"""
Tools the assistant can call. Each tool has:
  1. a JSON schema (what the model sees, so it knows when/how to call it)
  2. a Python function (what actually runs when it's called)

To add a new tool: write the function, add its schema to TOOL_DEFINITIONS,
and add one line to the dispatch table at the bottom. Nothing else in the
codebase needs to change.

Deliberately NOT included: arbitrary code/shell execution. A tool like that
would let anything the model reads -- a search result, a fetched web page,
even a file it opened -- potentially inject instructions that run on your
real machine. Every tool below is narrow and sandboxed on purpose: the
calculator can only do arithmetic, and file access is locked to one folder.
"""
import ast
import datetime
import operator as op
import re
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from app.config import settings
from app.long_term_memory import add_fact as _save_long_term_fact

# --- Tool implementations -------------------------------------------------

WORKSPACE_DIR = Path(settings.db_path).parent / "workspace"

_SAFE_OPS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Pow: op.pow, ast.Mod: op.mod, ast.USub: op.neg, ast.FloorDiv: op.floordiv,
}


def _safe_eval(node):
    """Evaluate a restricted arithmetic AST. No names, no calls, no attribute
    access -- so this can't be abused to run arbitrary code, unlike eval()."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Expression contains disallowed syntax")


def calculator(expression: str) -> dict:
    try:
        tree = ast.parse(expression, mode="eval").body
        return {"result": _safe_eval(tree)}
    except Exception as e:
        return {"error": f"Could not evaluate '{expression}': {e}"}


def current_time(timezone: str = "UTC") -> dict:
    # Kept dependency-free: real timezone support belongs to a proper zoneinfo
    # lookup, this is intentionally the simple version to start from.
    now = datetime.datetime.now(datetime.timezone.utc)
    return {"utc_time": now.isoformat(), "note": "Server returns UTC regardless of requested timezone in this starter version."}


_WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


def get_weather(location: str, units: str = "fahrenheit", when: str = "today") -> dict:
    """Weather for a place name, via Open-Meteo (free, no API key).
    `when` is 'today' for current conditions or 'tomorrow' for the next
    day's forecast high/low."""
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1},
            timeout=10,
        ).json()
    except requests.RequestException as e:
        return {"error": f"Could not reach the geocoding service: {e}"}

    results = geo.get("results")
    if not results:
        return {"error": f"Couldn't find a location matching '{location}'"}

    place = results[0]
    lat, lon = place["latitude"], place["longitude"]
    temp_unit = "fahrenheit" if units.lower().startswith("f") else "celsius"
    location_label = f"{place.get('name')}, {place.get('admin1', '')} {place.get('country', '')}".strip()
    unit_symbol = "°F" if temp_unit == "fahrenheit" else "°C"

    if when.lower() == "tomorrow":
        try:
            forecast = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                    "temperature_unit": temp_unit,
                    "timezone": "auto",
                    "forecast_days": 2,
                },
                timeout=10,
            ).json()
        except requests.RequestException as e:
            return {"error": f"Could not reach the weather service: {e}"}

        daily = forecast.get("daily", {})
        if len(daily.get("time", [])) < 2:
            return {"error": "Tomorrow's forecast isn't available for this location right now."}

        code = daily["weather_code"][1]
        return {
            "location": location_label,
            "date": daily["time"][1],
            "high": f"{daily['temperature_2m_max'][1]}{unit_symbol}",
            "low": f"{daily['temperature_2m_min'][1]}{unit_symbol}",
            "conditions": _WMO_CODES.get(code, "unknown"),
        }

    try:
        forecast = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "temperature_unit": temp_unit,
                "wind_speed_unit": "mph" if temp_unit == "fahrenheit" else "kmh",
            },
            timeout=10,
        ).json()
    except requests.RequestException as e:
        return {"error": f"Could not reach the weather service: {e}"}

    current = forecast.get("current", {})
    code = current.get("weather_code")

    return {
        "location": location_label,
        "temperature": f"{current.get('temperature_2m')}{unit_symbol}",
        "conditions": _WMO_CODES.get(code, "unknown"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m"),
    }


def web_search(query: str, max_results: int = 5) -> dict:
    """Free, keyless web search via DuckDuckGo."""
    try:
        results = DDGS().text(query, max_results=max_results)
    except Exception as e:
        return {"error": f"Search failed: {e}"}
    if not results:
        return {"results": [], "note": "No results found."}
    return {
        "results": [
            {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
            for r in results
        ]
    }


def fetch_page(url: str) -> dict:
    """Fetch a web page and return its readable text, stripped of scripts,
    styles, and markup. Truncated to keep the response a reasonable size."""
    if not url.lower().startswith(("http://", "https://")):
        return {"error": "URL must start with http:// or https://"}
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Robert/1.0"})
        response.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Could not fetch '{url}': {e}"}

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text(separator="\n").strip())

    max_chars = 6000
    truncated = len(text) > max_chars
    return {
        "url": url,
        "text": text[:max_chars],
        "truncated": truncated,
    }


def _safe_workspace_path(filename: str) -> Path | None:
    """Resolve a filename to inside WORKSPACE_DIR, refusing anything that
    would escape it (e.g. '../../secrets.txt')."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    candidate = (WORKSPACE_DIR / filename).resolve()
    if WORKSPACE_DIR.resolve() not in candidate.parents and candidate != WORKSPACE_DIR.resolve():
        return None
    return candidate


def write_file(filename: str, content: str) -> dict:
    """Create or overwrite a file inside Robert's sandboxed workspace folder
    (never anywhere else on disk)."""
    path = _safe_workspace_path(filename)
    if path is None:
        return {"error": "Invalid filename -- must stay inside the workspace folder."}
    try:
        path.write_text(content)
    except OSError as e:
        return {"error": f"Could not write file: {e}"}
    return {"saved": str(path.relative_to(WORKSPACE_DIR))}


def read_file(filename: str) -> dict:
    """Read a file from Robert's sandboxed workspace folder."""
    path = _safe_workspace_path(filename)
    if path is None:
        return {"error": "Invalid filename -- must stay inside the workspace folder."}
    if not path.exists():
        return {"error": f"'{filename}' doesn't exist in the workspace."}
    try:
        return {"content": path.read_text(errors="replace")}
    except OSError as e:
        return {"error": f"Could not read file: {e}"}


def list_files() -> dict:
    """List every file currently in Robert's sandboxed workspace folder."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    files = [p.name for p in WORKSPACE_DIR.iterdir() if p.is_file()]
    return {"files": files, "workspace_path": str(WORKSPACE_DIR)}


def remember(fact: str) -> dict:
    """Save a fact that should persist across sessions -- name, preferences,
    ongoing projects, anything worth Robert recalling in a future chat."""
    return _save_long_term_fact(fact)


# --- Schemas the model sees --------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "calculator",
        "description": "Evaluate a basic arithmetic expression (+, -, *, /, //, %, **). Use for any math instead of computing it yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "e.g. '(42 * 7) / 3'"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "current_time",
        "description": "Get the current date and time in UTC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "description": "Reserved for future use; currently always returns UTC."},
            },
        },
    },
    {
        "name": "get_weather",
        "description": "Get the weather for a city or place name, either right now or tomorrow's forecast. Use this for any weather question instead of guessing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name, e.g. 'Mount Royal, NJ' or 'Tokyo'"},
                "units": {"type": "string", "enum": ["fahrenheit", "celsius"], "description": "Defaults to fahrenheit."},
                "when": {"type": "string", "enum": ["today", "tomorrow"], "description": "Defaults to today (current conditions)."},
            },
            "required": ["location"],
        },
    },
    {
        "name": "remember",
        "description": "Save an important fact about the user for future conversations -- their name, preferences, ongoing projects, or anything else worth recalling later, even in a brand new chat. Call this whenever the user shares something worth remembering long-term.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "A concise, self-contained fact, e.g. \"User's name is Michael\" or 'User prefers metric units.'"},
            },
            "required": ["fact"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for current information -- news, facts you're unsure of, anything that might have changed recently. Use this instead of guessing about anything time-sensitive.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Short, specific search query."},
                "max_results": {"type": "integer", "description": "Defaults to 5."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_page",
        "description": "Fetch the readable text content of a specific web page URL. Use after web_search when you need the full content of a specific result, or when the user gives you a direct link.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL including http:// or https://"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "write_file",
        "description": "Save content to a file in Robert's local workspace folder -- use for notes, drafts, or anything the user asks you to create as a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "e.g. 'notes.txt' or 'draft.md' -- no folders/paths."},
                "content": {"type": "string", "description": "Full file content to write."},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file back from Robert's local workspace folder.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Name of the file to read."},
            },
            "required": ["filename"],
        },
    },
    {
        "name": "list_files",
        "description": "List every file currently saved in Robert's local workspace folder.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_DISPATCH = {
    "calculator": calculator,
    "current_time": current_time,
    "get_weather": get_weather,
    "remember": remember,
    "web_search": web_search,
    "fetch_page": fetch_page,
    "write_file": write_file,
    "read_file": read_file,
    "list_files": list_files,
}


def execute_tool(name: str, tool_input: dict) -> dict:
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"Unknown tool '{name}'"}

    start = time.perf_counter()
    try:
        result = fn(**tool_input)
    except TypeError as e:
        result = {"error": f"Bad arguments for '{name}': {e}"}
    duration_ms = (time.perf_counter() - start) * 1000

    try:
        from app.audit_log import log_tool_call

        log_tool_call(name, tool_input, result, duration_ms)
    except Exception:
        pass  # logging should never break a tool call

    return result
