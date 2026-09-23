from app.tools import TOOL_DEFINITIONS, calculator, current_time, execute_tool


def test_calculator_basic_arithmetic():
    assert calculator("2 + 2")["result"] == 4
    assert calculator("(10 - 4) * 3")["result"] == 18
    assert calculator("2 ** 10")["result"] == 1024


def test_calculator_rejects_unsafe_input():
    result = calculator("__import__('os').system('echo hi')")
    assert "error" in result


def test_calculator_rejects_names():
    result = calculator("open('/etc/passwd')")
    assert "error" in result


def test_current_time_returns_iso_string():
    result = current_time()
    assert "utc_time" in result
    assert "T" in result["utc_time"]


def test_execute_tool_dispatches_correctly():
    result = execute_tool("calculator", {"expression": "3 * 3"})
    assert result["result"] == 9


def test_weather_tool_is_registered():
    names = [t["name"] for t in TOOL_DEFINITIONS]
    assert "get_weather" in names


def test_weather_tool_parses_a_successful_response(monkeypatch):
    """Mocked, not a live network call -- keeps the suite fast and
    deterministic regardless of Open-Meteo's availability."""
    import app.tools as tools_module

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return FakeResponse({"results": [{"name": "Testville", "admin1": "NJ", "country": "US", "latitude": 1.0, "longitude": 2.0}]})
        return FakeResponse({"current": {"temperature_2m": 72.0, "relative_humidity_2m": 40, "wind_speed_10m": 5, "weather_code": 1}})

    monkeypatch.setattr(tools_module.requests, "get", fake_get)

    result = tools_module.get_weather("Testville")
    assert "Testville" in result["location"]
    assert result["conditions"] == "mainly clear"
    assert result["temperature"] == "72.0°F"


def test_weather_tool_handles_unknown_location(monkeypatch):
    import app.tools as tools_module

    class FakeResponse:
        def json(self):
            return {"results": []}

    monkeypatch.setattr(tools_module.requests, "get", lambda *a, **k: FakeResponse())

    result = tools_module.get_weather("Nowhereville")
    assert "error" in result


def test_weather_tool_tomorrow_forecast(monkeypatch):
    import app.tools as tools_module

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return FakeResponse({"results": [{"name": "Testville", "admin1": "NJ", "country": "US", "latitude": 1.0, "longitude": 2.0}]})
        return FakeResponse(
            {
                "daily": {
                    "time": ["2026-08-04", "2026-08-05"],
                    "temperature_2m_max": [80.0, 85.0],
                    "temperature_2m_min": [65.0, 68.0],
                    "weather_code": [1, 61],
                }
            }
        )

    monkeypatch.setattr(tools_module.requests, "get", fake_get)

    result = tools_module.get_weather("Testville", when="tomorrow")
    assert result["date"] == "2026-08-05"
    assert result["high"] == "85.0°F"
    assert result["conditions"] == "slight rain"


def test_web_search_returns_results(monkeypatch):
    import app.tools as tools_module

    class FakeDDGS:
        def text(self, query, max_results=5):
            return [{"title": "Example", "href": "https://example.com", "body": "An example result"}]

    monkeypatch.setattr(tools_module, "DDGS", FakeDDGS)

    result = tools_module.web_search("test query")
    assert result["results"][0]["title"] == "Example"
    assert result["results"][0]["url"] == "https://example.com"


def test_web_search_handles_failure(monkeypatch):
    import app.tools as tools_module

    class FailingDDGS:
        def text(self, query, max_results=5):
            raise RuntimeError("network down")

    monkeypatch.setattr(tools_module, "DDGS", FailingDDGS)

    result = tools_module.web_search("test query")
    assert "error" in result


def test_fetch_page_rejects_non_http_url():
    import app.tools as tools_module

    result = tools_module.fetch_page("file:///etc/passwd")
    assert "error" in result


def test_fetch_page_extracts_text(monkeypatch):
    import app.tools as tools_module

    class FakeResponse:
        text = "<html><head><style>body{}</style></head><body><script>evil()</script><p>Hello world</p></body></html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(tools_module.requests, "get", lambda *a, **k: FakeResponse())

    result = tools_module.fetch_page("https://example.com")
    assert "Hello world" in result["text"]
    assert "evil()" not in result["text"]


def test_write_and_read_file_roundtrip(tmp_path, monkeypatch):
    import app.tools as tools_module

    monkeypatch.setattr(tools_module, "WORKSPACE_DIR", tmp_path / "workspace")

    write_result = tools_module.write_file("notes.txt", "hello from robert")
    assert write_result["saved"] == "notes.txt"

    read_result = tools_module.read_file("notes.txt")
    assert read_result["content"] == "hello from robert"


def test_write_file_blocks_path_traversal(tmp_path, monkeypatch):
    import app.tools as tools_module

    monkeypatch.setattr(tools_module, "WORKSPACE_DIR", tmp_path / "workspace")

    result = tools_module.write_file("../../evil.txt", "escape attempt")
    assert "error" in result


def test_read_file_missing_file(tmp_path, monkeypatch):
    import app.tools as tools_module

    monkeypatch.setattr(tools_module, "WORKSPACE_DIR", tmp_path / "workspace")

    result = tools_module.read_file("does_not_exist.txt")
    assert "error" in result


def test_list_files(tmp_path, monkeypatch):
    import app.tools as tools_module

    monkeypatch.setattr(tools_module, "WORKSPACE_DIR", tmp_path / "workspace")
    tools_module.write_file("a.txt", "content a")
    tools_module.write_file("b.txt", "content b")

    result = tools_module.list_files()
    assert set(result["files"]) == {"a.txt", "b.txt"}


def test_execute_tool_unknown_tool():
    result = execute_tool("does_not_exist", {})
    assert "error" in result


def test_execute_tool_bad_arguments():
    result = execute_tool("calculator", {"wrong_arg": "1+1"})
    assert "error" in result
