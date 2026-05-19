from __future__ import annotations

import re

# 部门名允许后跟括号后缀，如 "学生工作部（处）"、"党委学生工作部(学生处)"
# 兼容全角括号（U+FF08/U+FF09）和半角括号
_DEPT_CORE = r"[A-Za-z一-鿿]{1,20}部"
_DEPT_PAREN = r"(?:[(（][A-Za-z一-鿿]{1,10}[)）])?"
_DEPT_FULL = _DEPT_CORE + _DEPT_PAREN

DEPARTMENT_PATTERN = re.compile(_DEPT_FULL)
DEPARTMENT_NOTICE_PATTERN = re.compile(_DEPT_FULL + r"通知")
DATE_LINE_PATTERN = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")
DEPARTMENT_LINE_PATTERN = re.compile(_DEPT_FULL)


def is_notice_request(text: str) -> bool:
    normalized = text.strip().lower()
    return ("通知" in text) or ("公告" in text) or ("notice" in normalized) or ("announcement" in normalized)


def has_department_in_request(text: str) -> bool:
    return DEPARTMENT_PATTERN.search(text) is not None


def enforce_notice_skill_defaults(user_text: str, assistant_text: str) -> str:
    if not is_notice_request(user_text):
        return assistant_text
    if not assistant_text.strip():
        return assistant_text

    dept_in_request = has_department_in_request(user_text)
    lines = assistant_text.splitlines()

    # ── 部门名替换（仅在用户未指定部门时） ──
    if not dept_in_request:
        first_non_empty = -1
        for idx, line in enumerate(lines):
            if line.strip():
                first_non_empty = idx
                break

        if first_non_empty == -1:
            return "xx部通知"

        title_line = lines[first_non_empty].strip()
        if "通知" in title_line:
            wrapped_bold = title_line.startswith("**") and title_line.endswith("**")
            core = title_line.strip("*").strip()
            if DEPARTMENT_NOTICE_PATTERN.search(core):
                core = DEPARTMENT_NOTICE_PATTERN.sub("xx部通知", core, count=1)
            else:
                core = "xx部通知"
            lines[first_non_empty] = f"**{core}**" if wrapped_bold else core
        else:
            lines.insert(first_non_empty, "xx部通知")
            lines.insert(first_non_empty + 1, "")

    # ── 落款行检测（始终执行） ──
    date_index = -1
    for idx in range(len(lines) - 1, -1, -1):
        if DATE_LINE_PATTERN.fullmatch(lines[idx].strip()):
            date_index = idx
            break

    sig_index = -1
    for idx in range(len(lines) - 1, -1, -1):
        candidate = lines[idx].strip().strip("*")
        if "通知" in candidate:
            continue
        if DEPARTMENT_LINE_PATTERN.fullmatch(candidate):
            sig_index = idx
            break

    # ── 部门名替换（仅在用户未指定时） ──
    if not dept_in_request:
        if sig_index != -1:
            raw = lines[sig_index]
            lines[sig_index] = DEPARTMENT_PATTERN.sub("xx部", raw, count=1)
        elif date_index != -1:
            lines.insert(date_index, "xx部")
            sig_index = date_index
            date_index += 1
        else:
            lines.extend(["", "---", "xx部"])
            sig_index = len(lines) - 1

    # ── 无落款内容则无需右对齐 ──
    if sig_index == -1 and date_index == -1:
        return "\n".join(lines)

    # ── 构建右对齐 HTML 签名块（始终执行） ──
    sig_start = min(i for i in (sig_index, date_index) if i != -1)
    if sig_start > 0 and lines[sig_start - 1].strip() in ("---", "***"):
        sig_start -= 1
    sig_end = max(i for i in (sig_index, date_index) if i != -1)

    sig_html_parts = []
    if sig_index != -1:
        raw = lines[sig_index].strip()
        is_bold = raw.startswith("**") and raw.endswith("**")
        dept = raw.strip("*").strip()
        sig_html_parts.append(f"<strong>{dept}</strong>" if is_bold else dept)
    if date_index != -1:
        sig_html_parts.append(lines[date_index].strip().strip("*"))

    sig_html = '<div align="right">' + "<br>".join(sig_html_parts) + "</div>"
    lines = lines[:sig_start] + [sig_html] + lines[sig_end + 1:]

    return "\n".join(lines)
