from __future__ import annotations

import json
import subprocess


DEFAULT_BASE_URL = "http://localhost:3001"
DEFAULT_WORKSPACE = "ai"


def anythingllmquery(message: str, api_key: str, base_url: str = DEFAULT_BASE_URL) -> dict:
    message = (message or "").strip()
    if not message:
        return {"ok": False, "error": "message is required"}
    url = base_url.rstrip("/") + f"/api/v1/workspace/{DEFAULT_WORKSPACE}/chat"
    payload = json.dumps({"message": message}, ensure_ascii=False)

    args = [
        "curl",
        "-sS",
        "-X",
        "POST",
        url,
        "-H",
        "Content-Type: application/json",
        "-d",
        payload,
    ]
    if api_key:
        args.insert(-2, "-H")
        args.insert(-2, f"Authorization: Bearer {api_key}")

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "error": result.stderr.strip() or "curl failed",
            "status": result.returncode,
        }

    stdout = result.stdout.strip()
    if not stdout:
        return {"ok": False, "error": "empty response"}
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid json", "raw": stdout}
    return {"ok": True, "data": data}


def tool_spec() -> dict:
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

