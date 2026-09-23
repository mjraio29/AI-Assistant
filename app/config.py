"""
Central configuration. All settings are read from environment variables so
the same code runs locally, in CI, and in production without edits.
"""
import os
import sys
from pathlib import Path

# Load a local .env file if python-dotenv is installed and a .env exists.
# When packaged with PyInstaller, __file__ points inside a temp extraction
# folder, not next to the actual .exe -- so look next to sys.executable
# instead whenever running frozen.
try:
    from dotenv import load_dotenv

    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
    else:
        app_dir = Path(__file__).resolve().parent.parent

    env_path = app_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


class Settings:
    # --- Groq (OpenAI-compatible API) ---
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    model: str = os.getenv("ASSISTANT_MODEL", "llama-3.3-70b-versatile")
    max_output_tokens: int = int(os.getenv("ASSISTANT_MAX_TOKENS", "1024"))

    # --- Behavior ---
    system_prompt_path: Path = Path(__file__).parent / "prompts" / "system.md"
    max_history_messages: int = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
    max_tool_iterations: int = int(os.getenv("MAX_TOOL_ITERATIONS", "5"))

    # --- Storage ---
    db_path: str = os.getenv("ASSISTANT_DB_PATH", str(Path(__file__).parent.parent / "assistant.db"))

    # --- RAG (optional) ---
    rag_enabled: bool = os.getenv("RAG_ENABLED", "false").lower() == "true"
    rag_collection_dir: str = os.getenv("RAG_COLLECTION_DIR", str(Path(__file__).parent.parent / "rag_store"))
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "4"))

    # --- API server ---
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))


settings = Settings()


def require_api_key() -> str:
    """Raise a clear error if the API key is missing, instead of failing
    deep inside an SDK call with a cryptic auth error."""
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key "
            "from console.groq.com/keys, or export GROQ_API_KEY in your shell."
        )
    return settings.groq_api_key
