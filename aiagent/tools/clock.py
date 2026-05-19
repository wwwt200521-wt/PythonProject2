from __future__ import annotations

from datetime import datetime
from typing import Any


def get_system_datetime() -> dict[str, Any]:
    now_local = datetime.now().astimezone()
    return {
        "iso": now_local.isoformat(),
        "date": now_local.strftime("%Y-%m-%d"),
        "time": now_local.strftime("%H:%M:%S"),
        "weekday": now_local.strftime("%A"),
        "timezone": str(now_local.tzinfo),
        "timestamp": int(now_local.timestamp()),
    }


def tool_spec() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "get_system_datetime",
            "description": "Get current system date and time from local runtime environment.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    }

