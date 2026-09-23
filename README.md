# AI-Assistant

# Robert

<p align="center"> <img src="assets/robert-logo.png" alt="Robert Logo" width="150"/> </p> <h1 align="center">Robert</h1> <p align="center">A full-featured personal AI desktop assistant</p>

A custom Groq-powered assistant, built as an engineered system rather than
a thin API wrapper: persistent memory, function calling (tools), optional
retrieval-augmented generation, a FastAPI service layer, and a native
desktop app.

## Why this exists

Anyone can call `client.messages.create()` in a loop and call it a chatbot.
This project is about the parts around that call that turn it into an
assistant:

- **Memory** -- conversations persist across requests, scoped per session,
  stored in SQLite (swap for Postgres/Redis at scale). On top of that,
  Robert has *long-term* memory: facts saved with the `remember` tool
  persist across every session and app restart, so a brand new chat still
  knows your name.
- **Tools** -- the model can call real functions instead of guessing at
  answers it should compute or look up: a sandboxed calculator, a clock,
  live weather, free web search, web page fetching, and a local file
  workspace where Robert can create and read files. The tool-calling loop
  in `app/groq_client.py` handles multi-step tool use automatically.
- **RAG (optional)** -- ingest your own `.txt`/`.md` documents and have the
  assistant ground its answers in them, with source citations.
- **Audit log** -- every tool call Robert makes is recorded (tool name,
  arguments, result, timestamp), viewable from the sidebar. A security
  habit worth having on anything that can act on your behalf.
- **A real service boundary** -- FastAPI in front, so this can be deployed,
  load-tested, and integrated with a frontend, rather than living only in a
  notebook.
- **An audit trail** -- every tool call (name, arguments, result, timing)
  is logged to SQLite, viewable in the desktop app's **🛡 Audit log** panel.
  This is the kind of record a security-conscious deployment would want,
  and it's what you'd pull up if you were investigating whether a tool call
  was ever hijacked via prompt injection.

## Architecture

```
User (web / CLI)
      |
      v
FastAPI backend  (app/main.py)
      |
      v
Orchestration layer  (app/groq_client.py)
   |        |          |
Memory    RAG        Tools
(SQLite) (Chroma)  (calculator, clock, ...)
      |
      v
  Groq API
```

Each turn: the user message is optionally augmented with retrieved context,
saved to memory, and sent to Groq along with recent history and tool
definitions. If Groq asks to use a tool, the tool runs locally and its
result is fed back in -- looping until Groq returns a plain-text answer.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set GROQ_API_KEY (free, no card required: console.groq.com/keys)
```

Run the API:

```bash
uvicorn app.main:app --reload
# POST http://localhost:8000/chat  {"message": "hi"}
```

Or the CLI:

```bash
python cli.py
```

Or the desktop app:

```bash
python -m desktop.main
```

## Desktop app: Robert

A native chat window (CustomTkinter) with a session sidebar, message
bubbles, threaded sending so the UI never freezes while waiting on the API,
a system tray icon, and an optional launch-at-login toggle. It talks
directly to `app.groq_client` -- same memory, same tools, same optional
RAG as the CLI and the FastAPI backend, no server required.

```
desktop/
  main.py            the GUI: sidebar, chat window, markdown rendering,
                       Memory / Audit log / Export windows, tray wiring
  markdown_render.py   bold / inline code / code block rendering for bubbles
  session_store.py    JSON-backed session list (titles, ordering) layered
                       on top of app.memory's SQLite storage
  tray.py              system tray icon (pystray): show/hide, quit, autostart toggle
  autostart.py         cross-platform "launch at login" (macOS/Linux/Windows)
  assets/               Robert's icon (generate_icon.py regenerates it)
  build.sh              packages main.py into a standalone executable (macOS/Linux)
  build.ps1             same, for Windows
```

Sessions persist across restarts (same SQLite DB as the CLI/API), so a
conversation started in the terminal can be continued in Robert's desktop
window and vice versa. Chat bubbles render **bold**, `inline code`, and
fenced code blocks, and each message has a Copy button. The sidebar has
three utility buttons:

- **🧠 Memory** -- everything Robert has saved with `remember`; delete
  individual facts or clear them all
- **🛡 Audit log** -- every tool call he's made, with arguments and results,
  most recent first
- **⭳ Export chat** -- saves the current conversation to a `.md` file

### Tray icon and launch at login

Closing the window hides Robert to the system tray instead of quitting --
right-click the tray icon for "Show Robert", "Start at login", and "Quit".
Tray support depends on your OS having a tray backend available (always
true on a normal macOS/Windows/Linux desktop); if it's unavailable for some
reason, Robert just runs as a normal window with no tray, no crash.

"Start at login" writes:
- **macOS**: a LaunchAgent plist to `~/Library/LaunchAgents`
- **Linux**: a `.desktop` file to `~/.config/autostart`
- **Windows**: a value under `HKCU\...\Run`

It points at the packaged executable if you've run `desktop/build.sh`,
otherwise falls back to `python -m desktop.main` so it still works during
development.

### Packaging as a standalone app

```bash
bash desktop/build.sh
```

This uses PyInstaller to produce a single executable in `dist/` --
`dist/Robert` on macOS/Linux, `dist/Robert.exe` on Windows, icon included.
The API key is still read from the environment or a `.env` file next to
the executable at runtime; it is never baked into the build.

Run tests:

```bash
pytest
```

## Enabling RAG

```bash
pip install chromadb
```

```bash
# .env
RAG_ENABLED=true
```

```python
from app.rag import ingest_documents
ingest_documents("./my_docs")   # indexes every .txt/.md file in the folder
```

From then on, every user message is automatically checked against the
document store and relevant chunks are appended to the prompt with their
source file, before being sent to Groq.

## Tools

| Tool | What it does |
|---|---|
| `calculator` | Arithmetic, via a restricted AST -- can't run arbitrary code |
| `current_time` | Current UTC date/time |
| `get_weather` | Live weather (today or tomorrow) for any city, via Open-Meteo |
| `web_search` | Free web search via DuckDuckGo, no API key |
| `fetch_page` | Reads a specific URL's text content |
| `write_file` / `read_file` / `list_files` | A sandboxed local workspace folder Robert can create and read files in |
| `remember` | Saves a fact to long-term memory (see above) |

**Deliberately not included: arbitrary code or shell execution.** Handing a
locally-running agent the ability to run arbitrary commands means anything
it reads -- a search result, a fetched web page, even a file it opened --
could smuggle in instructions that execute on your real machine (prompt
injection). Every tool above is narrow on purpose: the calculator only does
arithmetic, and file access is locked to one folder it can't escape. If you
add tools of your own, keep that same principle -- scope each one to
exactly what it needs and nothing more.

## Adding a new tool

1. Write the function in `app/tools.py`.
2. Add its JSON schema to `TOOL_DEFINITIONS`.
3. Register it in the `_DISPATCH` dict.

No changes needed anywhere else -- the orchestration loop discovers and
calls tools generically.

## Security notes

- The calculator tool evaluates expressions via a restricted AST walk
  (`app/tools.py::_safe_eval`), not `eval()` -- it can only do arithmetic,
  not execute arbitrary code, even if an attacker controls the input string.
- Tool inputs come from the model, which in turn can be influenced by
  untrusted content (e.g. retrieved documents, if RAG is enabled). Don't add
  tools that take destructive actions (file deletion, sending money, etc.)
  without an explicit human-confirmation step in front of them.
- If you're testing this assistant against prompt-injection or jailbreak
  attempts, it pairs naturally with an ATLAS-aligned red-teaming harness --
  point adversarial probes at the `/chat` endpoint and check whether tool
  calls or system-prompt leakage occur under adversarial inputs.

## Project structure

```
app/
  main.py            FastAPI routes
  groq_client.py     orchestration: memory + tools + RAG + Groq API loop
  memory.py          SQLite conversation storage (per-session)
  long_term_memory.py SQLite storage for facts that persist across sessions
  audit_log.py       SQLite log of every tool call (name, args, result)
  tools.py           tool schemas + implementations (calculator, weather, web search, files, remember, ...)
  rag.py             optional document retrieval
  config.py          environment-driven settings
  prompts/system.md  editable system prompt
cli.py               terminal chat client
desktop/             native desktop chat app (CustomTkinter) + packaging
tests/               pytest suite
```

## Next steps to extend this

- Streaming responses (`client.messages.stream`) for a snappier UI
- Swap SQLite for Postgres and add per-user auth
- Add more tools: web search, calendar, a code sandbox
- Add eval/red-team scripts to systematically test tool-call safety
