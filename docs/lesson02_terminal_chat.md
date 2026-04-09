# Lesson 02: 终端聊天 + 流式输出 + 历史上下文

本教学文档目标：
- 学会在终端循环读取用户输入的聊天内容
- 学会将历史对话自动追加到上下文中
- 学会使用 OpenAI 兼容接口进行流式输出
- 学会用 Ctrl+C 安全退出循环

## 学习目标

- 终端交互：用 `input()` 持续读取用户消息
- 历史记录：用 `messages` 列表保存多轮对话
- 流式输出：解析 `data:` 行并实时打印
- 循环控制：捕获 `KeyboardInterrupt` 退出

## 预期脚本位置

建议创建新脚本：`practice02/terminal_chat_stream.py`

## 设计要点

1. 读取 `.env`：沿用 `practice01/run_llm.py` 的环境读取方法
2. 初始化历史：`messages = [{"role": "system", "content": "..."}]`
3. 循环读入用户输入：
   - 空输入跳过
   - `Ctrl+C` 触发退出
4. 构造请求体：
   - `model`
   - `messages`（包含历史）
   - `stream: true`
5. 发起请求并流式读取：
   - 按行读取响应
   - 解析以 `data:` 开头的 JSON 行
   - 发现 `[DONE]` 结束本轮流
6. 输出与历史更新：
   - 用户输入加入 `messages`
   - 模型回复拼接成完整字符串后加入 `messages`

## 伪代码

```python
messages = [{"role": "system", "content": "你是一个有帮助的助手"}]

while True:
    try:
        user_text = input("你: ").strip()
        if not user_text:
            continue

        messages.append({"role": "user", "content": user_text})
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        # 发起请求并流式解析输出
        assistant_text = stream_chat(base_url, api_key, payload)
        messages.append({"role": "assistant", "content": assistant_text})

    except KeyboardInterrupt:
        print("\n已退出。")
        break
```

## 关键实现提示

- 流式响应通常以 `data:` 行输出 JSON 增量
- 累积 `delta.content` 作为本轮回复内容
- 处理网络错误时输出错误信息并继续下一轮输入

## 自测清单

- 输入多轮对话后，模型能基于历史上下文回答
- 流式输出能逐步显示文本（不是一次性输出）
- `Ctrl+C` 退出时不会抛出未处理异常

