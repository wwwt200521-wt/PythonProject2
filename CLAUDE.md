# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个统一的 AI 终端助手，核心包为 `aiagent`。支持两种入口：终端命令行聊天（`chatclient.py`）和 Web UI（`server.py` FastAPI + SSE）。底层对接 OpenAI 兼容 API，通过链式工具调用（chained tool call）编排多个工具完成任务。

## 常用命令

```powershell
# 安装依赖
python -m pip install fastapi uvicorn

# 安装测试依赖
python -m pip install pytest

# 运行全部测试
python -m pytest -q

# 运行单个测试文件
python -m pytest tests/test_retry.py -q

# 启动 Web 服务（http://127.0.0.1:8000）
python server.py

# 启动终端聊天模式
python -m aiagent.chatclient
```

## 核心架构

### 两个入口，同一套引擎

- `server.py`：FastAPI Web 服务器，通过 SSE 流式推送 token 和 tool_call 事件。前端静态文件在 `frontend/index.html`。
- `aiagent/chatclient.py`：终端命令行主循环，`main()` 函数除了 I/O 方式不同，其余流程与 server 完全一致。

### 请求处理流程

```
用户输入
  → routing.py（意图检测，构建带约束的增强请求）
    → force_skills 快路径（写作类直接调 LLM）
    → web_summary 快路径（URL+总结/写入直接抓取→总结→落盘）
    → workflow.executechainedtoolcall（链式工具调用主循环）
      → 每轮迭代构造分析 prompt → LLM 决策 → 执行工具 → 反馈结果
      → 直到 LLM 返回 done=true 或达到最大迭代次数
```

### 链式工具调用引擎（workflow.py）

`executechainedtoolcall()` 是整个系统的核心。它在循环中：
1. 将用户请求 + 已执行工具历史拼接为分析 prompt
2. 发送给 LLM（带 tools 定义，tool_choice=auto）
3. 如果 LLM 返回 tool_calls：执行工具，将结果加入 messages，继续循环
4. 如果 LLM 返回 JSON `{"done": true, "answer": "..."}`：结束，返回答案
5. 超出 `maxiterations` 后尝试 auto_finalize 兜底

### 路由层（routing.py）

基于关键词匹配检测用户意图，在原始输入上追加【执行约束】段落，强制 LLM 必须调用指定工具：

- `should_force_skills_check()`：写作/内容创作触发词（"写一篇"、"读后感"、"公众号" 等）→ 强制调 list_skills + read_skill
- `should_force_search()`：身份/名字类关键词 → 强制调 search_history
- `should_force_list_anythingllm_files()`："知识库" + "文件" + "列出" → 强制调 list_anythingllm_workspace_files
- `should_force_list_workspace_files()`："本地" + "项目" + "文件" + "列出" → 强制调 list_dir
- `extract_windows_file_path()` + `request_mentions_file_write()`：检测是否要求输出到具体文件路径

### 工具系统

每个工具模块在 `aiagent/tools/` 下，遵循统一约定：
- `tool_specs()` 返回 LLM function calling 的 tools 定义列表
- `tool_dispatch()` 返回 `{"tool_name": callable}` 映射
- `format_tool_result()` 将工具返回值格式化为字符串供 LLM 阅读

`workflow.build_tools()` 汇总所有工具的 tool_specs；`workflow._build_dispatch_map()` 汇总所有 dispatch。

`tooling.py` 提供工具调用的横切关注点：参数校验（validate_tool_arguments）、工作区范围限制（enforce_workspace_scope_for_fs）、审计日志（execute_with_tool_audit）。

### LLM 客户端（llm_client.py）

使用 Python 标准库 `urllib`（无第三方 HTTP 依赖），对接 OpenAI 兼容的 `/chat/completions` 端点。支持流式（SSE）和非流式两种模式。`call_llm_with_retry` 通过 `retry.py` 的装饰器实现指数退避重试（仅对 5xx 和网络错误重试）。

### 会话管理与会话压缩

`conversation_messages` 是带 system prompt 的完整消息列表。`history_compress.py` 在对话轮数 >5 或总字符数 >3000 时触发压缩：
1. 从 `_raw_messages` 中提取新增的对话文本（transcript）
2. 调用 LLM 按 5W 规则提取关键事实，存入历史日志（history tool）
3. 将前 75% 的旧消息压缩为一条 system 摘要消息

server.py 中此逻辑在 `_maybe_compress_history()` 中；chatclient.py 中内联在主循环里。

### 通知规范化（notice.py）

当用户请求涉及"通知"/"公告"但未指定部门时，自动将部门名替换为 "xx部"，并以 HTML 格式右对齐签名区。

## 配置

从项目根目录 `.env` 加载。必需项：`OPENAI_BASE_URL`、`OPENAI_MODEL`。`RuntimeConfig` 定义在 `aiagent/env.py`。

## 测试

测试文件在 `tests/` 下，使用 pytest。测试直接导入 `aiagent` 模块，无 mock 框架，部分测试需要真实 API 端点（属于集成测试）。

## 关键设计约束

- `FILESYSTEM_WORKSPACE_ONLY=true`（默认）时，所有文件系统工具只能访问项目根目录内的路径
- 工具调用审计日志写入 `runtime/tool_calls.jsonl`（可通过 `TOOL_CALL_AUDIT_ENABLED` 关闭）
- LLM 可能不返回原生 tool_calls 而是返回 JSON 文本；`response_parser.py` 兼容两种格式
- `web_summary.py` 作为快路径独立于主工具链：检测到 URL + "总结/写入" 关键词后直接 fetch→summarize→write，不走 chained tool call
