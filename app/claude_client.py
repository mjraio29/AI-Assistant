"""
The orchestration layer: takes a user message, assembles context (history +
retrieved docs), calls Claude, executes any tool calls it asks for, and loops
until Claude returns a plain text answer.

This is the piece that turns "an API call" into "an assistant" -- everything
else in the package supports this loop.
"""
from anthropic import Anthropic

from app.config import require_api_key, settings
from app.memory import get_history, save_message
from app.tools import TOOL_DEFINITIONS, execute_tool

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=require_api_key())
    return _client


def _system_prompt() -> str:
    return settings.system_prompt_path.read_text()


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


def chat(session_id: str, user_message: str) -> str:
    """Run one full conversational turn for `session_id` and return the
    assistant's final text reply. Persists both the user turn and the
    assistant turn to memory before returning."""
    client = _get_client()

    augmented_message = _maybe_augment_with_rag(user_message)
    save_message(session_id, "user", augmented_message)

    messages = get_history(session_id)

    for _ in range(settings.max_tool_iterations):
        response = client.messages.create(
            model=settings.model,
            max_tokens=settings.max_tokens,
            system=_system_prompt(),
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            final_text = "".join(block.text for block in response.content if block.type == "text")
            save_message(session_id, "assistant", [b.model_dump() for b in response.content])
            return final_text

        # Claude wants to call one or more tools. Run them and feed results back.
        assistant_blocks = [b.model_dump() for b in response.content]
        messages.append({"role": "assistant", "content": assistant_blocks})
        save_message(session_id, "assistant", assistant_blocks)

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = execute_tool(block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                }
            )

        messages.append({"role": "user", "content": tool_results})
        save_message(session_id, "user", tool_results)

    return "I wasn't able to finish that after several tool calls -- try rephrasing or breaking the request into smaller pieces."
