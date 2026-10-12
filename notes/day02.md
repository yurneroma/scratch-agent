# Day 2: 流式输出

## 做了什么

把 `messages.create()` 换成 `messages.stream()`，用事件流 (streaming) 实时打印回复。

```python
with client.messages.stream(model=..., messages=messages) as stream:
    content_blocks, stop_reason, usage = print_stream(stream)
```

## 学到了什么

**1. 流式事件的结构：start → delta → stop**

Anthropic 的流式协议发送一系列事件：

- `message_start`：包含 `input_tokens`
- `content_block_start`：开始一个新的内容块（text / thinking / tool_use），给出 `type`
- `content_block_delta`：增量内容（`text_delta` / `thinking_delta`）
- `content_block_stop`：一个内容块结束
- `message_delta`：包含 `stop_reason` 和 `output_tokens`
- `message_stop`：整条消息结束

如果有多个内容块（比如先 thinking 再 text），就是：
```
message_start
  content_block_start(thinking) → delta → delta → stop
  content_block_start(text) → delta → delta → stop
message_delta
message_stop
```

**2. 必须从 delta 事件重建完整的 content blocks**

非流式接口返回的是 `response.content`，一个完整的 `ContentBlock` 列表。流式接口只发增量，所以要自己拼：

```python
content_blocks.append({"type": "text", "text": ""})
# ... 每次 delta 来了就 += delta.text
```

最后把这个列表存进 `messages`，和非流式的结果格式保持一致。第 3 天的 tool_use 块也要这样重建。

**3. thinking 块可以实时显示**

现在能看到模型在"想什么"：
```
💭 The user is asking me to calculate 17 * 23.
17 * 23 = 17 * 20 + 17 * 3 = 340 + 51 = 391
...
```

这比第 1 天只看到最终回复更透明。代价是 thinking 内容很长，占用大量输出 token（161 个 token 里大部分是 thinking）。

**4. `usage.input_tokens` 在流式里是 0（这是个坑）**

实测输出 `in=0`，但肯定不是免费的。GLM 的流式接口在 `message_start` 事件里返回了 `input_tokens`，但我当前的实现没有正确读取到这个值。需要改成：

```python
case "message_start":
    usage["input_tokens"] = event.message.usage.input_tokens
```

不过既然现在能看到流式输出了，证明 GLM 的 Anthropic 兼容层至少实现了基本的流式协议。

**5. 流式的用户体验更好**

不用等整个回复生成完才看到内容，尤其是长回复时，体验差别很明显。这就是为什么所有生产级 agent 都用流式。
