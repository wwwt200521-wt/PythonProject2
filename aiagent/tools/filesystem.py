import json
from pathlib import Path
from typing import Callable


def _resolve_in_dir(dir_path: str, name: str) -> Path:
    base = Path(dir_path).expanduser().resolve()
    target = (base / name).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("Path escapes the target directory") from exc
    return target


def list_dir(dir_path: str) -> dict:
    base = Path(dir_path).expanduser().resolve()
    if not base.exists() or not base.is_dir():
        raise ValueError("Directory does not exist")

    items = []
    for entry in base.iterdir():
        stat = entry.stat()
        items.append(
            {
                "name": entry.name,
                "path": str(entry),
                "type": "dir" if entry.is_dir() else "file",
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return {"directory": str(base), "items": items}


def rename_file(dir_path: str, old_name: str, new_name: str) -> dict:
    src = _resolve_in_dir(dir_path, old_name)
    dst = _resolve_in_dir(dir_path, new_name)
    if not src.exists():
        raise ValueError("Source file does not exist")
    if src.is_dir():
        raise ValueError("Source path is a directory, not a file")
    if dst.exists():
        raise ValueError("Target file already exists")
    src.rename(dst)
    return {"from": str(src), "to": str(dst)}


def delete_file(dir_path: str, filename: str) -> dict:
    target = _resolve_in_dir(dir_path, filename)
    if not target.exists():
        raise ValueError("File does not exist")
    if target.is_dir():
        raise ValueError("Target path is a directory, not a file")
    target.unlink()
    return {"deleted": str(target)}


def write_file(dir_path: str, filename: str, content: str, append: bool = False) -> dict:
    target = _resolve_in_dir(dir_path, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as handle:
        handle.write(content)
    return {
        "path": str(target),
        "bytes": len(content.encode("utf-8")),
        "append": append,
    }


def read_file(dir_path: str, filename: str) -> dict:
    target = _resolve_in_dir(dir_path, filename)
    if not target.exists():
        raise ValueError("File does not exist")
    if target.is_dir():
        raise ValueError("Target path is a directory, not a file")
    content = target.read_text(encoding="utf-8")
    return {"path": str(target), "content": content}


def create_dir(dir_path: str, name: str) -> dict:
    target = _resolve_in_dir(dir_path, name)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target)}


def tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_dir",
                "description": "List files in a directory with basic attributes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string", "description": "Target directory path"}
                    },
                    "required": ["dir_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rename_file",
                "description": "Rename a file inside a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string"},
                        "old_name": {"type": "string"},
                        "new_name": {"type": "string"},
                    },
                    "required": ["dir_path", "old_name", "new_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_file",
                "description": "Delete a file inside a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string"},
                        "filename": {"type": "string"},
                    },
                    "required": ["dir_path", "filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a file and write content in a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string"},
                        "filename": {"type": "string"},
                        "content": {"type": "string"},
                        "append": {
                            "type": "boolean",
                            "description": "Append to the file instead of overwrite",
                        },
                    },
                    "required": ["dir_path", "filename", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file's content in a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string"},
                        "filename": {"type": "string"},
                    },
                    "required": ["dir_path", "filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_dir",
                "description": "Create a subdirectory inside a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string"},
                        "name": {"type": "string"},
                    },
                    "required": ["dir_path", "name"],
                },
            },
        },
    ]


def tool_dispatch() -> dict[str, Callable[..., dict]]:
    return {
        "list_dir": list_dir,
        "rename_file": rename_file,
        "delete_file": delete_file,
        "write_file": write_file,
        "read_file": read_file,
        "create_dir": create_dir,
    }


def format_tool_result(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)

