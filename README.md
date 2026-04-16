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

- `aiagent/chatclient.py`：统一终端对话主流程（历史压缩、工具路由、流式输出）。
- `aiagent/history_compress.py`：历史对话压缩与总结逻辑。
- `aiagent/tools/filesystem.py`：文件系统工具（列目录、读写、删除、重命名、建目录）。
- `aiagent/tools/weather.py`：wttr.in 天气查询工具。
- `aiagent/tools/anythingllm.py`：AnythingLLM 查询工具。
- `aiagent/tools/history.py`：5W 历史记录写入与检索工具。

## 测试

```powershell
python -m pip install pytest
python -m pytest -q
```

## 说明

- 程序会从项目根目录读取 `.env`。
- OpenAI 兼容请求发送到 `{OPENAI_BASE_URL}/chat/completions`。
- AnythingLLM 鉴权使用 `ANYTHINGLLMAPIKEY`。
