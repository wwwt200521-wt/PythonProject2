from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib import parse

from aiagent.llm_client import call_llm_with_retry, stream_llm_call
from aiagent.tools.filesystem import tool_dispatch as fs_dispatch
from aiagent.tools.web import tool_dispatch as web_dispatch

FIRST_URL_PATTERN = re.compile(r"https?://[^\s]+", flags=re.IGNORECASE)
WINDOWS_ABS_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\r\n]+")


def extract_first_url(text: str) -> str:
    if not isinstance(text, str):
        return ""
    match = FIRST_URL_PATTERN.search(text)
    return match.group(0).strip() if match else ""


def extract_windows_file_path(text: str) -> str:
    if not isinstance(text, str):
        return ""
    match = WINDOWS_ABS_PATH_PATTERN.search(text)
    if not match:
        return ""
    path = match.group(0).strip().strip("'\"`")
    path = path.rstrip("，。；;,.!！）)]")
    return path


def request_mentions_file_write(text: str) -> bool:
    normalized = (text or "").lower()
    keywords = ("写入", "保存", "落盘", "输出到文件", "write", "save", "file")
    return any(keyword in normalized or keyword in (text or "") for keyword in keywords)


def request_mentions_summary(text: str) -> bool:
    normalized = (text or "").lower()
    keywords = ("总结", "摘要", "总结成", "概括", "summary", "summarize", "summarise")
    return any(keyword in normalized or keyword in (text or "") for keyword in keywords)


def build_web_summary_filename(url: str) -> str:
    parsed = parse.urlparse(url or "")
    segments = [segment for segment in parsed.path.split("/") if segment]
    candidate = segments[-1] if segments else parsed.netloc
    candidate = re.sub(r"\.[A-Za-z0-9]+$", "", candidate)
    candidate = re.sub(r"[^A-Za-z0-9_-]+", "_", candidate).strip("_")
    if not candidate:
        candidate = "web"
    return f"{candidate}_summary.md"


def extract_latest_web_content(executed_steps: list[dict[str, Any]], target_url: str) -> tuple[str, str]:
    for step in reversed(executed_steps):
        if step.get("tool_name") != "fetch_web_content":
            continue
        raw_result = step.get("result", "")
        if not isinstance(raw_result, str) or not raw_result.strip():
            continue
        try:
            parsed = json.loads(raw_result)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        fetched_url = str(parsed.get("url", "")).strip()
        if target_url and fetched_url and fetched_url != target_url:
            continue
        content = str(parsed.get("content", "")).strip()
        if not content:
            continue
        title = str(parsed.get("title", "")).strip()
        return title, content
    return "", ""


def summarize_web_content(base_url: str, api_key: str, model: str, max_tokens: int, url: str, title: str, content: str, *, on_token=None) -> str:
    prompt = (
        f"请基于以下网页内容生成中文总结，必须输出恰好 10 条要点。\n\n"
        f"URL: {url}\n"
        f"标题: {title or '（无标题）'}\n\n"
        "要求：\n"
        "1. 每条要点一行，以“1.”到“10.”编号。\n"
        "2. 只基于给定内容，不要编造。\n"
        "3. 语言简洁、信息密度高。\n\n"
        f"网页文本：\n{content}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个网页内容总结助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    return stream_llm_call(base_url, api_key, payload, on_token=on_token)


def auto_finalize_web_summary_to_file(
    userrequest: str,
    executed_steps: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    model: str,
    max_tokens: int,
    *,
    on_token=None,
) -> str:
    target_url = extract_first_url(userrequest)
    target_path = extract_windows_file_path(userrequest)
    if not target_url or not target_path:
        return ""

    title, content = extract_latest_web_content(executed_steps, target_url)
    if not content:
        try:
            fetched = web_dispatch()["fetch_web_content"](url=target_url)
        except Exception:
            fetched = {}
        if isinstance(fetched, dict):
            title = str(fetched.get("title", "")).strip()
            content = str(fetched.get("content", "")).strip()
    if not content:
        return ""

    summary = summarize_web_content(base_url, api_key, model, max_tokens, target_url, title, content, on_token=on_token)
    if not summary:
        return ""

    target = Path(target_path)
    write_result = fs_dispatch()["write_file"](
        dir_path=str(target.parent),
        filename=target.name,
        content=summary,
        append=False,
    )
    return f"已完成总结并写入本地文件：{write_result.get('path', str(target))}"


def build_web_summary_request(user_text: str, project_root: Path) -> str:
    target_url = extract_first_url(user_text)
    if not target_url:
        return ""
    if not (request_mentions_file_write(user_text) or request_mentions_summary(user_text)):
        return ""

    target_path = extract_windows_file_path(user_text)
    if target_path:
        return user_text

    default_filename = build_web_summary_filename(target_url)
    default_path = str(project_root / "runtime" / "web_summaries" / default_filename)
    return user_text + "\n" + default_path

