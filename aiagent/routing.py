from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiagent.web_summary import extract_windows_file_path, request_mentions_file_write

FORCE_SEARCH_KEYWORDS: tuple[str, ...] = ("名字", "姓名", "叫啥", "我是谁", "身份")

WRITING_SKILL_TRIGGERS: tuple[str, ...] = (
    "写一篇", "写个", "写一份", "写段",
    "读后感", "书评", "影评", "心得",
    "公众号", "稿子", "作文", "文章",
    "续写", "扩写", "按我的风格写",
)


def is_search_trigger(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("/search") or "查找聊天历史" in stripped or "搜索聊天历史" in stripped


def should_route_for_tools(text: str) -> bool:
    return bool((text or "").strip())


def should_force_search(text: str) -> bool:
    return any(keyword in text for keyword in FORCE_SEARCH_KEYWORDS)


def should_force_list_workspace_files(text: str) -> bool:
    normalized = text.strip().lower()
    local_hit = "本地" in normalized or "项目" in normalized or "当前目录" in normalized
    workspace_hit = "工作区" in normalized or "workspace" in normalized
    file_hit = "文件" in normalized or "file" in normalized
    list_hit = ("列出" in normalized) or ("查看" in normalized) or ("list" in normalized)
    all_hit = "所有" in normalized or "全部" in normalized or "all" in normalized
    return local_hit and workspace_hit and file_hit and (list_hit or all_hit)


def should_force_list_anythingllm_files(text: str) -> bool:
    normalized = text.strip().lower()
    workspace_hit = "工作区" in normalized or "workspace" in normalized
    file_hit = "文件" in normalized or "file" in normalized or "文档" in normalized
    list_hit = ("列出" in normalized) or ("查看" in normalized) or ("list" in normalized)
    all_hit = "所有" in normalized or "全部" in normalized or "all" in normalized
    anything_hit = "anythingllm" in normalized or "知识库" in normalized
    return anything_hit and workspace_hit and file_hit and (list_hit or all_hit)


def should_force_skills_check(text: str) -> bool:
    normalized = text.strip()
    return any(keyword in normalized for keyword in WRITING_SKILL_TRIGGERS)


def normalize_search_query(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("/search"):
        return stripped[len("/search") :].strip() or "查找聊天历史"
    return stripped


def build_chained_user_request(
    user_text: str,
    project_root: Path,
    force_search: bool = False,
    force_workspace_files: bool = False,
    force_anythingllm_files: bool = False,
    force_skills: bool = False,
) -> str:
    constraints = []

    if force_anythingllm_files:
        args = json.dumps({"workspace": "ai"}, ensure_ascii=False)
        constraints.append(f"必须调用工具 list_anythingllm_workspace_files，参数：{args}")

    if force_workspace_files:
        args = json.dumps({"dir_path": str(project_root)}, ensure_ascii=False)
        constraints.append(f"必须调用工具 list_dir，参数：{args}")

    if force_search:
        args = json.dumps({"query": user_text}, ensure_ascii=False)
        constraints.append(f"必须调用工具 search_history，参数：{args}")

    if force_skills:
        constraints.append(
            "你必须先调用 list_skills 查看可用的写作/内容技能，"
            "然后调用 read_skill 获取对应 skill 的详细规则、风格指南和示例，"
            "最后严格根据 skill 的规则完成写作任务。"
        )

    output_path = extract_windows_file_path(user_text)
    if output_path and request_mentions_file_write(user_text):
        target = Path(output_path)
        args = json.dumps({"dir_path": str(target.parent), "filename": target.name}, ensure_ascii=False)
        constraints.append(f"最终结果必须写入该本地文件，必须调用 write_file，参数至少包含：{args}")

    if not constraints:
        return user_text

    return user_text + "\n\n【执行约束】\n" + "\n".join(f"- {item}" for item in constraints)


def build_tool_call(query: str, call_id: str = "manual-search") -> dict[str, Any]:
    return {
        "type": "function",
        "id": call_id,
        "function": {
            "name": "search_history",
            "arguments": json.dumps({"query": query}, ensure_ascii=False),
        },
    }


def build_list_dir_tool_call(dir_path: str, call_id: str = "manual-list-dir") -> dict[str, Any]:
    return {
        "type": "function",
        "id": call_id,
        "function": {
            "name": "list_dir",
            "arguments": json.dumps({"dir_path": dir_path}, ensure_ascii=False),
        },
    }


def build_anythingllm_list_tool_call(workspace: str = "ai", call_id: str = "manual-anythingllm-list") -> dict[str, Any]:
    return {
        "type": "function",
        "id": call_id,
        "function": {
            "name": "list_anythingllm_workspace_files",
            "arguments": json.dumps({"workspace": workspace}, ensure_ascii=False),
        },
    }
