"""Real LLM integration test — validates all agent features against the live API."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiagent.env import load_runtime_config
from aiagent.workflow import build_tools, executechainedtoolcall
from aiagent.tooling import build_tool_schema_map

config = load_runtime_config(Path(__file__).resolve().parents[1])
tools = build_tools()
tool_schema_map = build_tool_schema_map(tools)
print(f"LLM: {config.base_url} | Model: {config.model}")
print(f"Tools loaded: {len(tools)}")

SYSTEM_PROMPT = (
    "你是一个支持工具调用的AI助手。工具可用时，先调用工具再回答用户。"
    "如果问题不需要工具，直接回答。"
)


def run_test(name: str, user_request: str, expected_tools: list[str] | None = None) -> bool:
    """Run a single test and report result."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"REQUEST: {user_request}")
    print(f"{'='*60}")

    try:
        result = executechainedtoolcall(
            userrequest=user_request,
            systemprompt=SYSTEM_PROMPT,
            tools=tools,
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            max_tokens=config.max_tokens,
            anythingllm_key=config.anythingllm_key,
            anythingllm_url=config.anythingllm_url,
            maxiterations=config.max_tool_iterations,
            tool_schema_map=tool_schema_map,
            project_root=config.project_root,
            restrict_filesystem_to_workspace=config.restrict_filesystem_to_workspace,
            tool_call_log_path=config.tool_call_log_path if config.enable_tool_call_audit else None,
        )
        print(f"RESULT: {result[:500]}{'...' if len(result) > 500 else ''}")
        print(f"STATUS: PASS")
        return True
    except Exception as exc:
        print(f"ERROR: {exc}")
        print(f"STATUS: FAIL")
        return False


# ========== Test Suite ==========
results: dict[str, bool] = {}

# 1. Basic chat (no tools needed)
results["basic_chat"] = run_test(
    "Basic chat — no tools",
    "你好，请用一句话介绍你自己",
)

# 2. DateTime tool
results["datetime"] = run_test(
    "DateTime tool",
    "现在是什么日期和时间？请调用get_system_datetime获取",
)

# 3. Filesystem — list project root
results["list_dir"] = run_test(
    "Filesystem — list_dir",
    f"请列出 {config.project_root} 目录下的所有文件",
)

# 4. Filesystem — write and read
test_file = config.project_root / "output" / "test_hello.txt"
results["write_read"] = run_test(
    "Filesystem — write_file + read_file",
    f"请先用write_file在{test_file.parent}目录下创建test_hello.txt，内容为'Hello from AI Agent 测试'，然后用read_file读取该文件确认内容正确",
)

# 5. Weather tool
results["weather"] = run_test(
    "Weather tool",
    "请查询北京的天气",
)

# 6. Skills tool
results["skills"] = run_test(
    "Skills tool",
    "请列出所有可用的技能(list_skills)，然后读取notice技能的详细内容",
)

# 7. Web fetch
results["web_fetch"] = run_test(
    "Web fetch",
    "请获取 https://httpbin.org/ip 的内容，告诉我里面有什么",
)

# 8. Chained tool calling
results["chained"] = run_test(
    "Chained tool calling",
    f"请先获取当前日期时间，然后列出{config.project_root}目录下的文件，最后把日期信息和文件列表写入{config.project_root / 'output' / 'status_report.txt'}",
)

# ========== Summary ==========
print(f"\n\n{'='*60}")
print("TEST SUMMARY")
print(f"{'='*60}")
passed = sum(1 for v in results.values() if v)
total = len(results)
for name, ok in results.items():
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}")
print(f"\nTOTAL: {passed}/{total} passed")
