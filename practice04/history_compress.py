from __future__ import annotations

import math
from typing import Callable


def count_rounds(messages: list[dict]) -> int:
    return sum(1 for message in messages if message.get("role") == "user")


def context_length(messages: list[dict]) -> int:
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
    return total


def should_compress(messages: list[dict], max_rounds: int = 5, max_chars: int = 3000) -> bool:
    return count_rounds(messages) > max_rounds or context_length(messages) > max_chars


def _format_transcript(messages: list[dict]) -> str:
    lines = []
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        if not content:
            continue
        if role == "user":
            prefix = "User"
        elif role == "assistant":
            prefix = "Assistant"
        elif role == "tool":
            prefix = "Tool"
        else:
            prefix = role or "Message"
        lines.append(f"{prefix}: {content}")
    return "\n".join(lines)


def _split_history(history: list[dict], summary_ratio: float = 0.75, keep_ratio: float = 0.30) -> tuple[list[dict], list[dict]]:
    if not history:
        return [], []
    total = len(history)
    summary_count = max(1, int(math.ceil(total * summary_ratio)))
    keep_count = max(1, int(math.ceil(total * keep_ratio)))
    summary_part = history[:summary_count]
    keep_part = history[-keep_count:]
    return summary_part, keep_part


def compress_history(
    messages: list[dict],
    summarize_func: Callable[[str], str],
    summary_ratio: float = 0.75,
    keep_ratio: float = 0.30,
) -> list[dict]:
    if not should_compress(messages):
        return messages

    system_messages = []
    idx = 0
    while idx < len(messages) and messages[idx].get("role") == "system":
        system_messages.append(messages[idx])
        idx += 1
    history = messages[idx:]

    summary_part, keep_part = _split_history(history, summary_ratio, keep_ratio)
    if not summary_part:
        return messages

    transcript = _format_transcript(summary_part)
    summary_text = summarize_func(transcript).strip()
    if not summary_text:
        return messages

    summary_message = {
        "role": "system",
        "content": "以下是之前对话的摘要，供后续参考：\n" + summary_text,
    }
    return system_messages + [summary_message] + keep_part

