from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from http.client import HTTPResponse
from typing import Any
from urllib import error, request

from aiagent.retry import retry_on_failure


def build_payload(model: str, messages: list[dict[str, Any]], max_tokens: int) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "stop": ["\n——\n⚠️ 重要提醒", "\n\n——\n⚠️ 重要提醒"],
    }


def iter_sse_lines(response: HTTPResponse) -> Iterator[str]:
    for raw in response:
        line = raw.decode("utf-8", errors="ignore").strip()
        if not line:
            continue
        if line.startswith("data:"):
            yield line[5:].strip()


def stream_llm_call(
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    *,
    on_token: Callable[[str], None] | None = None,
) -> str:
    """Stream an LLM chat completion, calling on_token for each content delta."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {**payload, "stream": True}
    body = json.dumps(payload).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(url, data=body, headers=headers, method="POST")

    try:
        with request.urlopen(req, timeout=120) as resp:
            chunks: list[str] = []
            for data in iter_sse_lines(resp):
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = event.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    chunks.append(content)
                    if on_token:
                        on_token(content)
            return "".join(chunks)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def call_llm(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(url, data=body, headers=headers, method="POST")

    try:
        with request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


@retry_on_failure(max_attempts=3, initial_delay=1.0, backoff_factor=2.0)
def call_llm_with_retry(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    return call_llm(base_url, api_key, payload)
