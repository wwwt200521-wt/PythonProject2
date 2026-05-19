# AI-Assistant — 统一 AI 终端助手

基于 OpenAI 兼容 API 的 AI 助手项目，核心包为 `aiagent`。支持**终端命令行聊天**和 **Web UI** 两种使用方式，通过链式工具调用（chained tool call）编排多个工具完成复杂任务。

## 环境准备

1. 创建并激活虚拟环境
2. 安装依赖
3. 将 `.env.example` 复制为 `.env` 并填写配置

## 快速开始（Windows PowerShell）

```powershell
# 1. 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 安装依赖
python -m pip install -r requirements.txt

# 3. 配置环境变量
Copy-Item .env.example .env
notepad .env

# 4. 启动终端聊天模式
python -m aiagent.chatclient

# 或者启动 Web 服务（访问 http://127.0.0.1:8000）
python server.py
```

## 项目结构

```
AI-Assistant/
├── aiagent/                    # 核心包
│   ├── chatclient.py           # 终端聊天主循环
│   ├── env.py                  # 环境变量加载与运行时配置
│   ├── llm_client.py           # LLM 请求/流式输出（urllib 实现）
│   ├── retry.py                # 指数退避重试装饰器
│   ├── response_parser.py      # 响应解析（兼容 JSON 文本与原生 tool_calls）
│   ├── routing.py              # 路由层：意图检测与约束注入
│   ├── notice.py               # 通知/公告部门规范化
│   ├── web_summary.py          # 网页抓取→总结→落盘快路径
│   ├── workflow.py             # 链式工具调用主循环（核心编排引擎）
│   ├── tooling.py              # 工具调用横切关注点（校验、审计、工作区限制）
│   ├── history_compress.py     # 对话历史压缩与摘要
│   └── tools/                  # 工具模块
│       ├── filesystem.py       # 文件系统操作（读写、列目录、删除、重命名）
│       ├── weather.py          # 天气查询（wttr.in）
│       ├── anythingllm.py      # AnythingLLM 知识库查询
│       ├── clock.py            # 系统日期时间
│       ├── history.py          # 5W 关键信息记录与搜索
│       ├── web.py              # 网页内容抓取
│       └── skills.py           # 写作技能管理
├── server.py                   # FastAPI Web 服务器（SSE 流式推送）
├── frontend/                   # Web UI 前端页面
│   ├── index.html
│   ├── app.js
│   └── style.css
├── tests/                      # 测试文件（pytest）
├── report.md                   # 项目报告
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量模板
├── .agents/                     # Claude Code 自定义 agent 技能
│   └── skills/
│       ├── init-spec/           # SPEC 驱动开发规划
│       ├── khazix-writer/       # 公众号长文写作（卡兹克风格）
│       └── notice/              # 通知公告撰写
└── CLAUDE.md                   # 项目架构说明（给 Claude Code 使用）
```

## 启动方式

| 方式 | 命令 | 说明 |
|---|---|---|
| 终端聊天 | `python -m aiagent.chatclient` | 命令行交互式对话 |
| Web 服务 | `python server.py` | 浏览器访问 `http://127.0.0.1:8000`，支持 SSE 实时推送 |

## 核心流程

```
用户输入 → routing.py（意图检测，追加执行约束）
  → 快路径（写作/URL 总结等直接处理）
  → workflow.executechainedtoolcall（链式工具调用主循环）
    → LLM 决策 → 执行工具 → 回填结果 → 继续迭代
    → 直到 LLM 返回 done=true 或达到最大轮数
```

## 主要模块说明

### 入口

- **chatclient.py**：终端主循环，处理用户输入/输出、会话上下文、历史压缩触发
- **server.py**：FastAPI Web 服务，通过 SSE 流式推送 token 和 tool_call 事件

### 引擎

- **workflow.py**：链式工具调用主循环，在每轮迭代中构造分析 prompt、调用 LLM、执行工具、回填结果
- **routing.py**：基于关键词匹配检测用户意图，在原始输入上追加执行约束，强制 LLM 调用指定工具
- **web_summary.py**：URL + "总结/写入" 关键词触发快路径，跳过工具链直接抓取→总结→落盘

### 工具系统

- **tooling.py**：参数校验（validate_tool_arguments）、工作区范围限制（enforce_workspace_scope）、审计日志（execute_with_tool_audit）
- **tools/**：每个工具模块提供统一的 `tool_specs / tool_dispatch / format_tool_result` 约定

### 基础设施

- **llm_client.py**：使用 Python 标准库 `urllib` 对接 OpenAI 兼容 API，支持流式（SSE）和非流式
- **retry.py**：指数退避重试装饰器（仅对 5xx 和网络错误重试）
- **response_parser.py**：LLM 可能返回 JSON 文本而非原生 tool_calls，此模块做兼容转换
- **history_compress.py**：对话轮数 >5 或总字符数 >3000 时触发压缩，按 5W 规则提取关键事实
- **notice.py**：通知/公告请求自动规范化部门名称为 "xx部"
- **env.py**：从 `.env` 加载 RuntimeConfig

## 配置说明

在 `.env` 中配置：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `OPENAI_BASE_URL` | API 端点地址 | 必填 |
| `OPENAI_MODEL` | 模型名称 | 必填 |
| `OPENAI_API_KEY` | API 密钥 | 必填 |
| `OPENAI_MAX_TOKENS` | 单次回复长度上限 | `8192` |
| `ANYTHINGLLMAPIKEY` | AnythingLLM 密钥 | 可选 |
| `ANYTHINGLLM_BASE_URL` | AnythingLLM 地址 | `http://localhost:3001` |
| `TOOL_CALL_MAX_ITERATIONS` | 链式工具调用最大轮数 | `8` |
| `FILESYSTEM_WORKSPACE_ONLY` | 文件操作仅限项目目录内 | `true` |
| `TOOL_CALL_AUDIT_ENABLED` | 启用工具调用审计日志 | `true` |

## 运行测试

```powershell
python -m pip install pytest
python -m pytest -q
```

## 注意事项

- 程序从项目根目录读取 `.env`，不要将真实密钥写入 `.env.example`
- 审计日志默认输出到 `Log\tool_calls.jsonl`
- `FILESYSTEM_WORKSPACE_ONLY=true` 时，文件系统工具仅允许访问项目根目录内路径
