from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib import error, request

from aiagent.retry import retry_on_failure


def _strip_html(raw_html: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw_html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_title(raw_html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_html)
    if not match:
        return ""
    return html.unescape(match.group(1)).strip()


def fetch_web_content(url: str, max_chars: int = 12000) -> dict[str, Any]:
    normalized = (url or "").strip()
    if not normalized:
        raise ValueError("URL is required")
    if not re.match(r"^https?://", normalized, flags=re.IGNORECASE):
        raise ValueError("Only http/https URLs are supported")

    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")

    @retry_on_failure(max_attempts=3, initial_delay=1.0, backoff_factor=2.0)
    def _do_fetch(target_url: str) -> tuple[str, str]:
        req = request.Request(
            target_url,
            headers={
                "User-Agent": "aiagent/1.0 (+https://github.com)",
                "Accept": "text/html, text/plain, application/xhtml+xml",
            },
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                raw_bytes = resp.read()
                ct = resp.headers.get("Content-Type", "")
                return raw_bytes.decode("utf-8", errors="ignore"), ct
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Failed to fetch URL: {exc.reason}") from exc

    raw_text, content_type = _do_fetch(normalized)

    title = ""
    if "html" in content_type.lower() or "<html" in raw_text.lower():
        title = _extract_title(raw_text)
        normalized_content = _strip_html(raw_text)
    else:
        normalized_content = re.sub(r"\s+", " ", raw_text).strip()

    truncated = len(normalized_content) > max_chars
    content = normalized_content[:max_chars] if truncated else normalized_content

    return {
        "url": normalized,
        "title": title,
        "content_type": content_type,
        "content": content,
        "truncated": truncated,
        "chars": len(content),
    }


def tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "fetch_web_content",
                "description": "Fetch text content from a website URL for reading or summarization.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Website URL, must start with http:// or https://",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Max returned content length, default 12000",
                        },
                    },
                    "required": ["url"],
                },
            },
        }
    ]


def tool_dispatch() -> dict[str, Any]:
    return {"fetch_web_content": fetch_web_content}


def format_tool_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False)

