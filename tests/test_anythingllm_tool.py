import json

from aiagent.tools.anythingllm import anythingllmquery, list_anythingllm_workspace_files


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_anythingllmquery_uses_http_request(monkeypatch) -> None:
    def fake_urlopen(req, timeout=30):
        assert timeout == 30
        assert req.get_method() == "POST"
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["message"] == "hello"
        return _FakeResponse(b'{"ok": true, "textResponse": "hi"}')

    monkeypatch.setattr("aiagent.tools.anythingllm.request.urlopen", fake_urlopen)
    result = anythingllmquery("hello", "token", "http://localhost:3001")

    assert result["ok"] is True
    assert result["data"]["textResponse"] == "hi"


def test_list_anythingllm_workspace_files_parses_documents(monkeypatch) -> None:
    payload = {
        "workspace": [
            {
                "documents": [
                    {
                        "filename": "alpha.md",
                        "docpath": "/docs/alpha.md",
                        "createdAt": "2026-01-01",
                        "metadata": '{"title":"Alpha"}',
                    }
                ]
            }
        ]
    }

    def fake_urlopen(req, timeout=30):
        assert timeout == 30
        assert req.get_method() == "GET"
        return _FakeResponse(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    monkeypatch.setattr("aiagent.tools.anythingllm.request.urlopen", fake_urlopen)
    result = list_anythingllm_workspace_files("token", "http://localhost:3001", "ai")

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["files"][0]["title"] == "Alpha"
    assert result["files"][0]["filename"] == "alpha.md"
