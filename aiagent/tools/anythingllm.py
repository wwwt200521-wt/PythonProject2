from __future__ import annotations

import json
from typing import Any
from urllib import error, parse, request

from aiagent.retry import retry_on_failure

DEFAULT_BASE_URL = "http://localhost:3001"
DEFAULT_WORKSPACE = "ai"


@retry_on_failure(max_attempts=3, initial_delay=1.0, backoff_factor=2.0)
def _request_json(url: str, *, method: str, api_key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = request.Request(url, data=data, headers=headers, method=method)

    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        message = f"HTTP {exc.code}: {detail}" if detail else f"HTTP {exc.code}"
        return {"ok": False, "error": message, "status": exc.code}
    except error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        return {"ok": False, "error": f"request failed: {reason}"}

    if not raw:
        return {"ok": False, "error": "empty response"}
    try:
        return {"ok": True, "data": json.loads(raw)}
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid json", "raw": raw}


def anythingllmquery(message: str, api_key: str, base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    message = (message or "").strip()
    if not message:
        return {"ok": False, "error": "message is required"}
    url = base_url.rstrip("/") + f"/api/v1/workspace/{DEFAULT_WORKSPACE}/chat"
    return _request_json(url, method="POST", api_key=api_key, payload={"message": message})


def list_anythingllm_workspace_files(api_key: str, base_url: str = DEFAULT_BASE_URL, workspace: str = DEFAULT_WORKSPACE) -> dict[str, Any]:
    workspace = (workspace or DEFAULT_WORKSPACE).strip() or DEFAULT_WORKSPACE
    workspace_slug = parse.quote(workspace, safe="")
    url = base_url.rstrip("/") + f"/api/v1/workspace/{workspace_slug}"
    result = _request_json(url, method="GET", api_key=api_key)
    if not result.get("ok"):
        return result

    payload = result.get("data", {})
    workspace_rows = payload.get("workspace") if isinstance(payload, dict) else None
    if not isinstance(workspace_rows, list) or not workspace_rows:
        return {"ok": False, "error": "workspace not found", "workspace": workspace}
    workspace_info = workspace_rows[0]
    documents = workspace_info.get("documents", [])

    files = []
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        meta_raw = doc.get("metadata", "{}")
        title = ""
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else {}
            if isinstance(meta, dict):
                title = str(meta.get("title", "")).strip()
        except json.JSONDecodeError:
            title = ""
        files.append(
            {
                "title": title or doc.get("filename", ""),
                "filename": doc.get("filename", ""),
                "docpath": doc.get("docpath", ""),
                "createdAt": doc.get("createdAt", ""),
            }
        )

    return {"ok": True, "workspace": workspace, "count": len(files), "files": files}


def tool_spec() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "anythingllmquery",
            "description": "Query AnythingLLM workspace via /api/v1/workspace/ai/chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The query message sent to AnythingLLM",
                    }
                },
                "required": ["message"],
            },
        },
    }


def list_files_tool_spec() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "list_anythingllm_workspace_files",
            "description": "List all files currently attached in an AnythingLLM workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "description": "Workspace slug, default is 'ai'",
                    }
                },
            },
        },
    }

