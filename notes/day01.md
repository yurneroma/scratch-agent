# Day 1: 多轮对话

## 做了什么

用 `messages` 列表保存对话历史，每轮把整个列表发给模型，回复存回去。

```python
messages.append({"role": "user", "content": user_input})
response = client.messages.create(model=..., messages=messages)
messages.append({"role": "assistant", "content": response.content})
```

## 学到了什么

**1. 模型没有状态，"记忆"就是每次重发的消息历史。**

实测：
- 第 1 轮说"我叫小明"，第 2 轮问"我叫什么"，回答"小明"；
- `/clear` 清空 `messages` 之后再问，回答"我不知道你的名字"。

说明 `messages` 就是模型能看到的全部上下文。清空了，模型什么都不记得。

**2. GLM 默认会返回 `thinking` 块，占用大量输出 token。**

`--ping` 的回复只有一个单词，却用了 36 个 token，其中 `thinking` 块占了大部分。`response.content` 里的结构是：

```python
[ContentBlock(type="thinking", thinking="..."), ContentBlock(type="text", text="pong")]
```

这些 thinking token 照样计费，而且下一轮会被原样发回去，占用输入 token。

**3. 输入 token 包含之前全部对话。**

第 2 轮的 `input_tokens=151`，远超输入的字数，因为第 1 轮的 user + assistant 内容（包括 thinking 块）都重发了。每轮的输入 token 都包含历史，所以对话越长，单轮成本越高。这就是第 9 天"上下文管理"要解决的核心问题。

**4. 必须保存完整的 `content` 块，不能只存文本。**

`messages.append({"role": "assistant", "content": response.content})`

第 3 天模型会返回 `tool_use` 块，协议要求原样发回去。如果只保存文本，tool use 会失败。

代价是 thinking 块也被重发了。要不要在回传前剥掉 thinking，留到第 9 天和上下文管理一起考虑。
