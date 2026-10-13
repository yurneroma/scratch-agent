# Day 3: 第一个工具与 agent 循环

## 做了什么

添加了第一个工具 `read_file`，并实现了 agent 循环：

```python
while iteration < max_iterations:
    response = client.messages.stream(..., tools=TOOLS)
    messages.append({"role": "assistant", "content": content_blocks})
    
    if stop_reason == "end_turn":
        break
    elif stop_reason == "tool_use":
        # 执行所有 tool_use 块
        tool_results = [...]
        messages.append({"role": "user", "content": tool_results})
        # 继续下一轮
```

## 学到了什么

**1. agent 的本质就是一个循环**

整个 agent 的核心逻辑：
- 发送请求 + 工具列表
- 如果 `stop_reason == "tool_use"`：执行工具 → 发回结果 → 重复
- 如果 `stop_reason == "end_turn"`：任务完成

这个循环就是"agent"和"普通聊天机器人"的区别。普通聊天一问一答就结束了，agent 可以自己决定要调哪些工具、调几次，直到解决问题。

**2. tool use 的往返协议**

模型返回 `tool_use` 块：
```python
{
    "type": "tool_use",
    "id": "toolu_01ABC...",
    "name": "read_file",
    "input": {"path": "ROADMAP.md"}
}
```

我们执行工具，把结果包装成 `tool_result`：
```python
{
    "type": "tool_result",
    "tool_use_id": "toolu_01ABC...",
    "content": "文件内容..."
}
```

发回去时，`role: "user"`，`content` 是 `tool_result` 列表。这是协议规定的格式，`tool_use_id` 必须和之前的 `tool_use` 块的 `id` 对应。

**3. 流式的 tool_use 块需要重建**

和 text/thinking 一样，`tool_use` 块也是通过 delta 事件发送的：
- `content_block_start`：给出 `id` 和 `name`
- `input_json_delta`：发送参数的 JSON 字符串片段
- `content_block_stop`：把累积的 JSON 字符串 `json.loads()` 成 `input` 字典

最终存进 `messages` 的格式和非流式完全一样。

**4. 一轮可以调多个工具**

测试时问"README.md 和 pyproject.toml 依赖了哪些包"，模型在同一个 assistant 回复里返回了两个 `tool_use` 块：
```python
content_blocks = [
    {"type": "tool_use", "name": "read_file", "input": {"path": "README.md"}, ...},
    {"type": "tool_use", "name": "read_file", "input": {"path": "pyproject.toml"}, ...},
]
```

我们循环处理所有 `tool_use` 块，把结果一起发回去。当前是串行执行，第 12 天会改成并行。

**5. 必须限制最大迭代次数**

设了 `max_iterations=10`，防止模型陷入无限循环（比如一直调工具但永远不满足 `end_turn`）。生产环境还要加超时控制。

**6. 工具描述直接影响模型行为**

`description: "Read the full content of a file. Use this when the user asks about a file or you need to see code/docs."`

这段描述告诉模型什么时候该用这个工具。如果写得模糊（比如只写"read a file"），模型可能不知道该不该调用。第 4 天加更多工具时，会更明显地感受到：**工具的 schema 和描述就是给模型看的"使用手册"**，写得好不好直接决定模型会不会用、用得对不对。

## 实测效果

```
> ROADMAP.md 这个文件里说第3天要做什么?
💭 (thinking...)
🔧 read_file({'path': 'ROADMAP.md'})
  → 2548 chars
💭 (thinking...)
根据 ROADMAP.md，第 3 天的任务是...
```

agent 自己决定需要读文件，读完再回答。用户只给了一个问题，agent 自己完成了"读文件 → 理解内容 → 回答"的完整流程。
