# PythonProject2

这是一个统一的 AI 终端助手项目，核心包为 `aiagent`。

## 环境准备

1. 创建并激活虚拟环境。
2. 将 `.env.example` 复制为 `.env` 并填写配置。
3. 启动命令行入口。

## 快速开始（Windows PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
notepad .env
python -m aiagent.cli
```

## 主要模块

- `server.py`：FastAPI Web 服务器，提供 REST API 和前端页面。
- `aiagent/chatclient.py`：终端主循环与会话驱动。
- `aiagent/env.py`：环境变量加载与运行时配置解析。
- `aiagent/llm_client.py`：LLM 请求/流式输出封装。
- `aiagent/routing.py`：路由与强制约束构建（不再依赖关键词大列表）。
- `aiagent/notice.py`：通知/公告默认部门规范化逻辑。
- `aiagent/web_summary.py`：网页抓取后总结并落盘的独立流程。
- `aiagent/workflow.py`：链式工具调用执行与工具运行编排。
- `aiagent/history_compress.py`：历史对话压缩与总结逻辑。
- `aiagent/tools/filesystem.py`：文件系统工具（列目录、读写、删除、重命名、建目录）。
- `aiagent/tools/weather.py`：wttr.in 天气查询工具。
- `aiagent/tools/anythingllm.py`：AnythingLLM 查询与工作区文件列表工具（urllib 实现）。
- `aiagent/tools/clock.py`：系统日期时间工具（用于回答今天日期、当前时间等问题）。
- `aiagent/tools/history.py`：5W 历史记录写入与检索工具。
- `aiagent/tools/web.py`：网站内容抓取工具（用于访问 URL 并提取文本供总结）。

## 测试

```powershell
python -m pip install pytest
python -m pytest -q
```

## 说明

- 程序会从项目根目录读取 `.env`。
- OpenAI 兼容请求发送到 `{OPENAI_BASE_URL}/chat/completions`。
- 可通过 `OPENAI_MAX_TOKENS` 调整单次回复长度上限（默认 `2048`）。
- AnythingLLM 鉴权使用 `ANYTHINGLLMAPIKEY`。
- `TOOL_CALL_MAX_ITERATIONS` 可控制链式工具调用最大轮数（默认 `8`）。
- `FILESYSTEM_WORKSPACE_ONLY=true` 时，文件系统工具仅允许访问项目根目录内路径。
- `TOOL_CALL_AUDIT_ENABLED=true` 时，工具调用审计日志写入 `TOOL_CALL_AUDIT_LOG_PATH`（默认 `runtime\tool_calls.jsonl`）。
