"""AI Agent Web Server (FastAPI + SSE).

Usage:
    pip install fastapi uvicorn
    python server.py

Then open http://127.0.0.1:8000 in a browser.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import uuid
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from aiagent.env import load_runtime_config
from aiagent.history_compress import compress_history, context_length, count_rounds, should_compress
from aiagent.llm_client import call_llm_with_retry, stream_llm_call
from aiagent.notice import enforce_notice_skill_defaults
from aiagent.routing import (
    build_chained_user_request,
    is_search_trigger,
    normalize_search_query,
    should_force_list_anythingllm_files,
    should_force_list_workspace_files,
    should_force_search,
    should_force_skills_check,
    should_route_for_tools,
)
from aiagent.tooling import build_tool_schema_map
from aiagent.tools.clock import get_system_datetime
from aiagent.tools.history import append_log_entries, read_log_text
from aiagent.tools.skills import list_skills as _list_skills, read_skill as _read_skill
from aiagent.web_summary import (
    auto_finalize_web_summary_to_file,
    build_web_summary_request,
)
from aiagent.workflow import (
    build_tools,
    build_transcript,
    executechainedtoolcall,
    extract_key_facts,
    summarize_history,
)

# --- Application setup ---

PROJECT_ROOT = Path(__file__).resolve().parent
config = load_runtime_config(PROJECT_ROOT)

app = FastAPI(title="AI Agent Web UI", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# In-memory conversation state
_system_prompt = (
    "对于内容创作类任务（文章、通知、读后感、公众号稿子等），必须先调用 list_skills 查看可用技能，"
    "再调用 read_skill 获取对应写作规范，最后按规范完成。"
    "涉及知识库和文档查询时，优先使用 AnythingLLM 相关工具和 search_history。"
)

conversation_messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt}]
_raw_messages: list[dict[str, Any]] = list(conversation_messages)
_tools = build_tools()
_tool_schema_map = build_tool_schema_map(_tools)
_conversation_id = str(uuid.uuid4())[:8]
_last_extracted_index = 0
_last_compress_rounds = 0
_last_compress_chars = 0

# Agent storage (persisted to file)
_AGENTS_FILE = PROJECT_ROOT / "data" / "agents.json"
_agents: dict[str, dict[str, Any]] = {}

def _load_agents() -> None:
    global _agents
    if _AGENTS_FILE.exists():
        try:
            _agents = json.loads(_AGENTS_FILE.read_text("utf-8"))
        except Exception:
            _agents = {}

def _save_agents() -> None:
    _AGENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AGENTS_FILE.write_text(json.dumps(_agents, ensure_ascii=False, indent=2), "utf-8")

_load_agents()


def _maybe_compress_history() -> None:
    global conversation_messages, _raw_messages, _last_extracted_index
    global _last_compress_rounds, _last_compress_chars

    cur_rounds = count_rounds(conversation_messages)
    cur_chars = context_length(conversation_messages)
    if not should_compress(conversation_messages):
        return
    if cur_rounds <= _last_compress_rounds and cur_chars <= _last_compress_chars:
        return

    transcript = build_transcript(_raw_messages, _last_extracted_index)
    if transcript:
        facts = extract_key_facts(config.base_url, config.api_key, config.model, transcript)
        if facts:
            append_log_entries(facts)
        _last_extracted_index = len(_raw_messages)

    conversation_messages = compress_history(
        conversation_messages,
        lambda t: summarize_history(config.base_url, config.api_key, config.model, t),
    )
    _last_compress_rounds = count_rounds(conversation_messages)
    _last_compress_chars = context_length(conversation_messages)


async def _yield_sse(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def _stream_tokens(
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    result: list[str],
    *,
    cancel_event: threading.Event | None = None,
) -> AsyncGenerator[str, None]:
    """Yield raw token strings. result[0] is set to the full text after exhaustion."""
    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _run() -> None:
        def _on_token(tok: str) -> None:
            loop.call_soon_threadsafe(q.put_nowait, tok)
        try:
            full = stream_llm_call(base_url, api_key, payload, on_token=_on_token)
            result.append(full)
        except Exception:
            result.append("")
        loop.call_soon_threadsafe(q.put_nowait, None)

    executor = ThreadPoolExecutor(max_workers=1)
    loop.run_in_executor(executor, _run)

    while True:
        tok = await q.get()
        if tok is None:
            executor.shutdown(wait=False)
            return
        if cancel_event and cancel_event.is_set():
            executor.shutdown(wait=False)
            return
        yield tok


async def _run_tool_chain_stream(
    chained_request: str,
    effective_user_text: str,
    user_text: str,
    effective_system: str,
    *,
    cancel_event: threading.Event | None = None,
) -> AsyncGenerator[str, None]:
    """Run tool chain in a thread, yielding SSE events in real time via queue."""
    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    result: list[str] = []

    def _run() -> None:
        def _emit_tc(tc: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(q.put_nowait, ("tool_call", tc))

        answer = executechainedtoolcall(
            userrequest=chained_request,
            systemprompt=effective_system,
            tools=_tools,
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            max_tokens=config.max_tokens,
            anythingllm_key=config.anythingllm_key,
            anythingllm_url=config.anythingllm_url,
            maxiterations=config.max_tool_iterations,
            tool_schema_map=_tool_schema_map,
            project_root=config.project_root,
            restrict_filesystem_to_workspace=config.restrict_filesystem_to_workspace,
            tool_call_log_path=config.tool_call_log_path,
            on_tool_call=_emit_tc,
            cancel_event=cancel_event,
        )

        if answer == "已达到最大迭代次数，但任务尚未完成。":
            fb_payload: dict[str, Any] = {
                "model": config.model,
                "messages": [{"role": "user", "content": effective_user_text}],
                "stream": False,
                "max_tokens": config.max_tokens,
            }
            fb_resp = call_llm_with_retry(config.base_url, config.api_key, fb_payload)
            fb_choice = fb_resp.get("choices", [{}])[0]
            fb_msg = fb_choice.get("message", fb_choice)
            answer = fb_msg.get("content") or fb_msg.get("reasoning_content") or ""

        answer = enforce_notice_skill_defaults(user_text, answer)
        result.append(answer)
        loop.call_soon_threadsafe(q.put_nowait, ("done", answer))

    executor = ThreadPoolExecutor(max_workers=1)
    loop.run_in_executor(executor, _run)

    while True:
        event_type, data = await q.get()
        if cancel_event and cancel_event.is_set():
            executor.shutdown(wait=False)
            return
        if event_type == "tool_call":
            yield await _yield_sse("tool_call", data)
        elif event_type == "done":
            full = data
            if full:
                for i in range(0, len(full), 4):
                    yield await _yield_sse("token", {"token": full[i : i + 4]})
                    await asyncio.sleep(0.04)
            yield await _yield_sse("done", {"answer": full})
            executor.shutdown(wait=False)
            return


async def _generate_chat_stream(
    effective_user_text: str,
    user_text: str,
    effective_system: str,
    *,
    request: Request,
) -> AsyncGenerator[str, None]:
    global conversation_messages, _raw_messages

    cancel_event = threading.Event()

    async def _monitor_disconnect() -> None:
        while not cancel_event.is_set():
            if await request.is_disconnected():
                cancel_event.set()
                return
            await asyncio.sleep(0.2)

    monitor_task = asyncio.create_task(_monitor_disconnect())

    streamed_tokens: list[str] = []

    def _on_token(tok: str) -> None:
        streamed_tokens.append(tok)

    tool_calls_log: list[dict[str, Any]] = []

    def _on_tool_call(tc: dict[str, Any]) -> None:
        tool_calls_log.append(tc)

    _t_start = time.perf_counter()

    # --- routing ---
    force_skills = should_force_skills_check(effective_user_text)
    force_search = is_search_trigger(user_text) or should_force_search(user_text)
    force_anythingllm = should_force_list_anythingllm_files(effective_user_text)
    force_workspace = should_force_list_workspace_files(effective_user_text)

    # --- force_skills: writing ---
    if force_skills:
        _now = get_system_datetime()
        effective_user_text = f"{effective_user_text}\n\n【当前系统时间】日期：{_now['date']}（{_now['weekday']}）"

    # --- web_summary ---
    web_req = build_web_summary_request(user_text, config.project_root)
    if web_req:
        from aiagent.web_summary import auto_finalize_web_summary_to_file
        result = auto_finalize_web_summary_to_file(
            userrequest=web_req, executed_steps=[],
            base_url=config.base_url, api_key=config.api_key,
            model=config.model, max_tokens=config.max_tokens,
        )
        result = enforce_notice_skill_defaults(user_text, result)
        yield await _yield_sse("done", {"answer": result})
        if result:
            conversation_messages.append({"role": "assistant", "content": result})
            _raw_messages.append({"role": "assistant", "content": result})
        monitor_task.cancel()
        return

    # --- chained tool call ---
    chained = build_chained_user_request(
        user_text=effective_user_text, project_root=config.project_root,
        force_search=force_search, force_workspace_files=force_workspace,
        force_anythingllm_files=force_anythingllm,
        force_skills=force_skills,
    )
    answer = ""
    async for line in _run_tool_chain_stream(
        chained_request=chained,
        effective_user_text=effective_user_text,
        user_text=user_text,
        effective_system=effective_system,
        cancel_event=cancel_event,
    ):
        yield line
        if "done" in line:
            try:
                done_data = json.loads(line[line.index("data:") + 5:].strip())
                answer = done_data.get("answer", answer)
            except Exception:
                pass

    if answer:
        conversation_messages.append({"role": "assistant", "content": answer})
        _raw_messages.append({"role": "assistant", "content": answer})

    monitor_task.cancel()


# ============================================================
# API routes
# ============================================================

@app.get("/api/health")
async def health():
    return {"status": "ok", "model": config.model, "conversation_id": _conversation_id}


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    user_text: str = (body.get("message") or "").strip()
    agent_id: str = (body.get("agent_id") or "").strip()
    if not user_text:
        raise HTTPException(400, "message is required")

    # Use agent's custom system prompt if selected
    effective_system = _system_prompt
    if agent_id and agent_id in _agents:
        effective_system = _agents[agent_id]["prompt"]

    # Replace system prompt if agent changed (simple approach: always set)
    if conversation_messages and conversation_messages[0]["role"] == "system":
        conversation_messages[0]["content"] = effective_system
    else:
        conversation_messages.insert(0, {"role": "system", "content": effective_system})

    user_message = {"role": "user", "content": user_text}
    conversation_messages.append(user_message)
    _raw_messages.append(user_message)
    _maybe_compress_history()

    return StreamingResponse(
        _generate_chat_stream(effective_user_text=user_text, user_text=user_text, effective_system=effective_system, request=request),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": _conversation_id},
    )


@app.post("/api/chat/regenerate")
async def regenerate(request: Request):
    global conversation_messages, _raw_messages

    body = await request.json()
    agent_id: str = (body.get("agent_id") or "").strip()

    # Use agent's custom system prompt if selected
    effective_system = _system_prompt
    if agent_id and agent_id in _agents:
        effective_system = _agents[agent_id]["prompt"]

    # Find the last user message and truncate everything after it
    last_user_idx = None
    for i in range(len(conversation_messages) - 1, -1, -1):
        if conversation_messages[i].get("role") == "user":
            last_user_idx = i
            break

    if last_user_idx is None:
        raise HTTPException(400, "No user message to regenerate from")

    user_text = str(conversation_messages[last_user_idx].get("content", ""))
    conversation_messages = conversation_messages[:last_user_idx]

    # Mirror truncation in raw messages
    last_raw_user_idx = None
    for i in range(len(_raw_messages) - 1, -1, -1):
        if _raw_messages[i].get("role") == "user":
            last_raw_user_idx = i
            break
    if last_raw_user_idx is not None:
        _raw_messages = _raw_messages[:last_raw_user_idx]

    return StreamingResponse(
        _generate_chat_stream(effective_user_text=user_text, user_text=user_text, effective_system=effective_system, request=request),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": _conversation_id},
    )


@app.get("/api/skills")
async def list_skills():
    result = _list_skills()
    return result


@app.get("/api/skills/{name}")
async def read_skill(name: str):
    try:
        result = _read_skill(name)
        return result
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/config")
async def get_config():
    key = config.api_key
    masked = key[:6] + "****" + key[-4:] if len(key) > 10 else "****"
    return {
        "base_url": config.base_url,
        "model": config.model,
        "api_key_masked": masked,
        "max_tokens": config.max_tokens,
        "max_tool_iterations": config.max_tool_iterations,
        "restrict_filesystem": config.restrict_filesystem_to_workspace,
        "tool_call_audit_enabled": config.enable_tool_call_audit,
    }


@app.get("/api/history")
async def get_history():
    try:
        text = read_log_text()
        lines = [json.loads(ln) for ln in text.strip().splitlines() if ln.strip()]
        return {"entries": lines, "total": len(lines)}
    except Exception:
        return {"entries": [], "total": 0}


@app.get("/api/conversation")
async def get_conversation():
    non_system = [m for m in conversation_messages if m.get("role") != "system"]
    return {"conversation_id": _conversation_id, "messages": non_system}


@app.delete("/api/conversation")
async def clear_conversation():
    global conversation_messages, _raw_messages
    global _last_extracted_index, _last_compress_rounds, _last_compress_chars
    conversation_messages = [{"role": "system", "content": _system_prompt}]
    _raw_messages = list(conversation_messages)
    _last_extracted_index = 0
    _last_compress_rounds = 0
    _last_compress_chars = 0
    return {"status": "cleared"}


# ---- Agent CRUD ----
@app.get("/api/agents")
async def list_agents():
    return [{"id": aid, "name": a["name"], "prompt": a["prompt"][:80] + ("..." if len(a.get("prompt","")) > 80 else "")} for aid, a in _agents.items()]


@app.post("/api/agents")
async def create_agent(request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    prompt = (body.get("prompt") or "").strip()
    if not name or not prompt:
        raise HTTPException(400, "name and prompt are required")
    aid = "a" + uuid.uuid4().hex[:10]
    _agents[aid] = {"name": name, "prompt": prompt, "created": datetime.now(timezone.utc).isoformat()}
    _save_agents()
    return {"id": aid, "name": name, "created": _agents[aid]["created"]}


@app.delete("/api/agents/{aid}")
async def delete_agent(aid: str):
    if aid not in _agents:
        raise HTTPException(404, "agent not found")
    del _agents[aid]
    _save_agents()
    return {"status": "deleted"}


@app.get("/api/skills/{name}/summary")
async def read_skill_summary(name: str):
    try:
        result = _read_skill(name)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(404, str(exc))

    content = result.get("content", "")
    # Parse YAML frontmatter
    desc = ""
    usage = ""
    if content.startswith("name:") or content.startswith("---"):
        # Find frontmatter description
        m = re.search(r"description:\s*(.+?)(?:\n|$)", content)
        if m:
            desc = m.group(1).strip()
    # Extract a usage hint from the first meaningful paragraph after frontmatter
    body_start = content.find("---", 4)
    if body_start != -1:
        body = content[body_start + 3:].strip()
    else:
        body = content.strip()
    # First non-empty, non-heading line as purpose
    lines = [l for l in body.split("\n") if l.strip() and not l.strip().startswith("#") and len(l.strip()) > 20]
    if lines:
        usage = lines[0].strip().lstrip("> ")[:120]

    return {
        "name": result["skill_name"],
        "description": desc or result["skill_name"],
        "usage_hint": usage,
        "content_length": len(content),
        "path": result.get("file_path", ""),
    }


@app.get("/api/audit-log")
async def get_audit_log(limit: int = 50):
    path = config.tool_call_log_path
    if not path or not path.exists():
        return {"entries": [], "total": 0}
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        entries = [json.loads(ln) for ln in lines if ln.strip()]
        return {"entries": entries[-limit:], "total": len(entries)}
    except Exception:
        return {"entries": [], "total": 0}


# ============================================================
# Static frontend
# ============================================================

FRONTEND_DIR = PROJECT_ROOT / "frontend"


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# Mount frontend static files (CSS, JS) — registered after routes so API routes take precedence
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend_static")


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
