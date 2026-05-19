from __future__ import annotations

import json
import re
from typing import Any

JSON_CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", flags=re.DOTALL)


def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        return tool_calls

    content = message.get("content", "")
    if not isinstance(content, str) or not content:
        return []

    payload = _extract_json_object(content)
    if isinstance(payload, dict):
        return _parse_json_tool_calls(payload)

    return []


def _extract_braced_json(text: str) -> dict[str, Any] | None:
    """通过括号配对找到最外层 {...} 并尝试解析，处理"前缀文字 + JSON"场景。"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    payload = json.loads(candidate)
                except json.JSONDecodeError:
                    return None
                if isinstance(payload, dict):
                    return payload
                return None
    return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None

    candidates = [stripped]
    code_block_match = JSON_CODE_BLOCK_PATTERN.findall(stripped)
    candidates.extend(code_block_match)

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    braced = _extract_braced_json(stripped)
    if isinstance(braced, dict):
        return braced

    decoder = json.JSONDecoder(strict=False)
    for start_index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(stripped[start_index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _parse_json_tool_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_calls: list[dict[str, Any]] = []

    raw_calls = payload.get("tool_calls")
    if isinstance(raw_calls, list):
        for index, raw_call in enumerate(raw_calls, start=1):
            if not isinstance(raw_call, dict):
                continue
            function_info = raw_call.get("function", raw_call)
            if not isinstance(function_info, dict):
                continue
            name = function_info.get("name") or raw_call.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            args = function_info.get("arguments", raw_call.get("arguments", {}))
            if not isinstance(args, dict):
                args = {}
            call_id = raw_call.get("id", f"json-tool-{index}")
            if not isinstance(call_id, str):
                call_id = f"json-tool-{index}"
            normalized_calls.append(
                {
                    "type": "function",
                    "id": call_id,
                    "function": {
                        "name": name.strip(),
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
            )
        return normalized_calls

    single_call = payload.get("tool_call")
    if isinstance(single_call, dict):
        name = single_call.get("name")
        args = single_call.get("arguments", {})
        if isinstance(name, str) and name.strip():
            if not isinstance(args, dict):
                args = {}
            normalized_calls.append(
                {
                    "type": "function",
                    "id": "json-tool-1",
                    "function": {
                        "name": name.strip(),
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
            )
        return normalized_calls

    tool_name = payload.get("tool") or payload.get("name")
    if isinstance(tool_name, str) and tool_name.strip():
        args = payload.get("arguments", payload.get("args", payload.get("parameters", {})))
        if not isinstance(args, dict):
            args = {}
        normalized_calls.append(
            {
                "type": "function",
                "id": "json-tool-1",
                "function": {
                    "name": tool_name.strip(),
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        )

    return normalized_calls


def parse_json_final_answer(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""

    keys = ("answer", "final_answer", "response", "output", "result")
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    done = payload.get("done")
    action = payload.get("action")
    if done is True or (isinstance(action, str) and action.lower() in {"done", "finish", "final", "complete", "completed"}):
        return ""
    return ""


def parse_tool_call_arguments(call: dict[str, Any]) -> dict[str, Any]:
    raw_args = call.get("function", {}).get("arguments", {})
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def looks_like_decision_json_text(text: str) -> bool:
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if "{" not in stripped:
        return False
    keys = ('"done"', '"tool_call"', '"tool_calls"', '"answer"', '"final_answer"')
    return any(key in stripped for key in keys)
