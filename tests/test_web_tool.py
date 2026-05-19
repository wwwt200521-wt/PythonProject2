import pytest

from aiagent.tools.web import fetch_web_content


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self._body = body
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_web_content_extracts_text_and_title(monkeypatch) -> None:
    html = b"""
    <html>
      <head>
        <title>Sample Page</title>
        <style>.hidden { display:none; }</style>
      </head>
      <body>
        <h1>Hello</h1>
        <script>console.log('x')</script>
        <p>World content.</p>
      </body>
    </html>
    """

    def fake_urlopen(_req, timeout=30):
        assert timeout == 30
        return _FakeResponse(html)

    monkeypatch.setattr("aiagent.tools.web.request.urlopen", fake_urlopen)
    result = fetch_web_content("https://example.com", max_chars=1000)

    assert result["url"] == "https://example.com"
    assert result["title"] == "Sample Page"
    assert "Hello World content." in result["content"]
    assert "console.log" not in result["content"]
    assert result["truncated"] is False


def test_fetch_web_content_rejects_non_http_url() -> None:
    with pytest.raises(ValueError, match="http/https"):
        fetch_web_content("file:///tmp/a.txt")

