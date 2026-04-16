from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def get_log_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "Log" / "log.txt"


def ensure_log_file(log_path: Path | None = None) -> Path:
    path = log_path or get_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def append_log_entries(entries: Iterable[dict], log_path: Path | None = None) -> dict:
    path = ensure_log_file(log_path)
    lines = []
    for entry in entries:
        if isinstance(entry, dict):
            lines.append(json.dumps(entry, ensure_ascii=False))
    if not lines:
        return {"appended": 0, "path": str(path)}

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return {"appended": len(lines), "path": str(path)}


def read_log_text(log_path: Path | None = None) -> str:
    path = ensure_log_file(log_path)
    return path.read_text(encoding="utf-8")


def tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "search_history",
                "description": "Search key facts in Log/log.txt based on a query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to search in the chat history log",
                        }
                    },
                    "required": ["query"],
                },
            },
        }
    ]


def format_tool_result(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)

