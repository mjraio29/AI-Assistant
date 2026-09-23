"""
The orchestration layer: takes a user message, assembles context (history +
retrieved docs), calls Groq (OpenAI-compatible chat completions), executes
any tool calls it asks for, and loops until Groq returns a plain text answer.

Groq's API mirrors OpenAI's chat completions format exactly, so this uses
the standard `openai` Python package pointed at Groq's base URL -- no
Groq-specific SDK required.
"""
import json

import openai
from openai import OpenAI

from app.audit_log import log_tool_call
from app.config import require_api_key, settings
from app.long_term_memory import get_facts
from app.memory import get_history, save_message
from app.tools import TOOL_DEFINITIONS, execute_tool

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=require_api_key(), base_url=settings.groq_base_url)
    return _client


def _system_prompt() -> str:
    base = settings.system_prompt_path.read_text()
    facts = get_facts()
    if not facts:
        return base
    facts_block = "\n".join(f"- {f['fact']}" for f in facts)
    return f"{base}\n\nKnown facts about the user from previous conversations:\n{facts_block}"


def _build_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOL_DEFINITIONS
    ]


def _maybe_augment_with_rag(user_message: str) -> str:
    if not settings.rag_enabled:
        return user_message
    from app.rag import retrieve  # imported lazily so chromadb stays optional

    hits = retrieve(user_message)
    if not hits:
        return user_message
    context = "\n\n".join(f"[Source: {h['source']}]\n{h['text']}" for h in hits)
    return (
        f"{user_message}\n\n"
        f"--- Retrieved context (use only if relevant, cite sources by name) ---\n{context}"
    )


def _history_to_messages(session_id: str) -> list[dict]:
    """Memory stores plain text per turn; translate straight into the
    OpenAI-style {role, content} shape Groq expects."""
    messages = [{"role": "system", "content": _system_prompt()}]
    for msg in get_history(session_id):
        content = msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
        messages.append({"role": msg["role"], "content": content})
    return messages


def _generate_with_retry(client: OpenAI, messages: list[dict], tools: list[dict]):
    """Groq occasionally emits a malformed tool call and rejects its own
    generation with a 'tool_use_failed' error -- a transient model glitch,
    not a real failure. Retry a couple times before giving up on tools
    entirely for this turn, so the person gets an answer either way."""
    last_error = None
    for attempt in range(3):
        try:
            return client.chat.completions.create(
                model=settings.model,
                messages=messages,
                tools=tools,
                max_tokens=settings.max_output_tokens,
            )
        except openai.APIError as e:
            is_tool_glitch = getattr(e, "code", None) == "tool_use_failed" or "tool_use_failed" in str(e)
            if not is_tool_glitch:
                raise
            last_error = e

    # Tools kept failing to generate cleanly -- fall back to a plain answer
    # without tool access rather than showing the person a raw API error.
    return client.chat.completions.create(
        model=settings.model,
        messages=messages
        + [{"role": "system", "content": "Tool calling is temporarily unavailable -- answer from what you know and say if you can't be certain."}],
        max_tokens=settings.max_output_tokens,
    )


def chat(session_id: str, user_message: str) -> str:
    """Run one full conversational turn for `session_id` and return the
    assistant's final text reply. Persists both the user turn and the
    assistant turn to memory before returning."""
    client = _get_client()

    augmented_message = _maybe_augment_with_rag(user_message)
    save_message(session_id, "user", augmented_message)

    messages = _history_to_messages(session_id)
    tools = _build_tools()

    for _ in range(settings.max_tool_iterations):
        response = _generate_with_retry(client, messages, tools)
        choice = response.choices[0].message

        if not choice.tool_calls:
            final_text = choice.content or ""
            save_message(session_id, "assistant", final_text)
            return final_text

        # Groq wants to call one or more tools. Run them and feed results back.
        messages.append(
            {
                "role": "assistant",
                "content": choice.content,
                "tool_calls": [tc.model_dump() for tc in choice.tool_calls],
            }
        )
        for tool_call in choice.tool_calls:
            args = json.loads(tool_call.function.arguments or "{}")
            result = execute_tool(tool_call.function.name, args)
            log_tool_call(session_id, tool_call.function.name, args, result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )

    return "I wasn't able to finish that after several tool calls -- try rephrasing or breaking the request into smaller pieces."
