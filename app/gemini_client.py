"""
The orchestration layer: takes a user message, assembles context (history +
retrieved docs), calls Gemini, executes any tool calls it asks for, and
loops until Gemini returns a plain text answer.

Memory here stores plain text per turn (not raw Gemini content objects) --
simpler than round-tripping the SDK's own types, and works identically for
the CLI, desktop app, and FastAPI backend.
"""
from google import genai
from google.genai import types

from app.config import require_api_key, settings
from app.memory import get_history, save_message
from app.tools import TOOL_DEFINITIONS, execute_tool

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=require_api_key())
    return _client


def _system_prompt() -> str:
    return settings.system_prompt_path.read_text()


def _build_tool() -> types.Tool:
    declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters_json_schema=t["input_schema"],
        )
        for t in TOOL_DEFINITIONS
    ]
    return types.Tool(function_declarations=declarations)


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


def _history_to_contents(session_id: str) -> list[types.Content]:
    """Memory stores role 'user'/'assistant' as plain text; Gemini expects
    role 'user'/'model'. Translate on the way in."""
    contents = []
    for msg in get_history(session_id):
        role = "model" if msg["role"] == "assistant" else "user"
        text = msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
    return contents


def chat(session_id: str, user_message: str) -> str:
    """Run one full conversational turn for `session_id` and return the
    assistant's final text reply. Persists both the user turn and the
    assistant turn to memory before returning."""
    client = _get_client()

    augmented_message = _maybe_augment_with_rag(user_message)
    save_message(session_id, "user", augmented_message)

    contents = _history_to_contents(session_id)
    tool = _build_tool()
    config = types.GenerateContentConfig(
        system_instruction=_system_prompt(),
        max_output_tokens=settings.max_output_tokens,
        tools=[tool],
    )

    for _ in range(settings.max_tool_iterations):
        response = client.models.generate_content(model=settings.model, contents=contents, config=config)

        if not response.function_calls:
            final_text = response.text or ""
            save_message(session_id, "assistant", final_text)
            return final_text

        # Gemini wants to call one or more tools. Run them and feed results back.
        contents.append(response.candidates[0].content)

        function_response_parts = []
        for call in response.function_calls:
            result = execute_tool(call.name, dict(call.args or {}))
            function_response_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )
        contents.append(types.Content(role="user", parts=function_response_parts))

    return "I wasn't able to finish that after several tool calls -- try rephrasing or breaking the request into smaller pieces."
