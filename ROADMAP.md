# scratch-agent 路线图

目标：从 0 手写一个类 Claude Code / OpenClaw 的 agent，**熟悉 agent 是如何构建的**。

## 原则

- **不用 agent 框架**（LangChain 等），直接调用模型 API 的 tool use 接口。
- **每个功能都必须能跑**，做完就能用。
- **评测前置**：第 5 天建立固定任务集，之后每加一个功能都跑一遍。
- **自举（dogfooding）**：从第 6 天起，用本 agent 开发它自己；用着哪里难受，就优先做哪个功能。
- **节奏按难度调整**：标 ⚠️ 的功能可能需要 2 天，轻量功能可以合并到同一天。
- **每天记笔记**：写到 `notes/dayNN.md`，重点回答"这个功能在解决什么问题"，而不只是"我写了什么"。

## 技术选型

- 语言：Python 3.11+，用 `uv` 管理依赖
- 模型：智谱 GLM Coding Plan（Anthropic 兼容协议，`https://open.bigmodel.cn/api/anthropic`），用官方 `anthropic` SDK
- 终端界面：前期用 `print`，第 19 天换成 `rich`

## 阶段一：核心循环（第 1–5 天）

| 天 | 功能 | 学到什么 | 状态 |
|---|---|---|---|
| 1 | 终端里的多轮对话：读输入、调 API，把历史存进 `messages` | 模型本身没有状态，"记忆"就是每次重发的消息历史 | ✅ |
| 2 | 流式输出，显示 token 用量 | 流式事件的结构，token 怎么计费 | ☐ |
| 3 | 第一个工具 `read_file`，加上 agent 循环：`while stop_reason == "tool_use"` | tool use 的往返协议，agent 的本质就是这个循环 | ☐ |
| 4 | 工具注册表；新增 `write_file`、`edit`（字符串替换）、`glob`、`grep` | 工具 schema 和描述怎么设计，以及它们如何影响模型行为 | ☐ |
| 5 | `bash` 工具（超时、输出截断）；**建立 3–5 个固定评测任务** | 给 agent 装上"手脚"；截断能防止长输出撑爆上下文；有了评测基线才能判断改动好坏 | ☐ |

> 里程碑：做完第 5 天，就有了一个能用的最小编程 agent。从这里开始自举。

## 阶段二：可靠性与安全（第 6–10 天）

| 天 | 功能 | 学到什么 | 状态 |
|---|---|---|---|
| 6 | 权限系统：危险操作先确认，支持白名单和 always-allow | agent 的安全边界放在哪里 | ☐ |
| 7 | system prompt 与环境注入：工作目录、操作系统、git 状态，以及加载 `AGENTS.md` | 上下文怎么装配 | ☐ |
| 8 | 错误处理：工具报错原样交还给模型，API 失败重试，限制最大轮数 | 模型能利用错误信息自己纠正 | ☐ |
| 9 ⚠️ | 上下文管理：统计 token、裁剪旧的工具输出，接近上限时自动摘要压缩 | 长任务中最核心的难点 | ☐ |
| 10 | 会话持久化：存成 JSONL，支持 `--resume` 接着聊 | 会话状态的序列化 | ☐ |

## 阶段三：高级能力（第 11–16 天）

| 天 | 功能 | 学到什么 | 状态 |
|---|---|---|---|
| 11 | Todo 与规划工具 | 用外部结构弥补模型注意力的不足 | ☐ |
| 12 | 并行工具调用（同一轮里的多个调用并发执行） | 并发与结果的顺序 | ☐ |
| 13 ⚠️ | 子 agent：在隔离的上下文中执行任务，只把结果带回来 | 用上下文隔离来节省主上下文 | ☐ |
| 14 | 持久记忆：基于文件，跨会话保留 | 怎么设计长期记忆 | ☐ |
| 15 | 斜杠命令与 Skills：从 markdown 文件按需加载指令 | 按需注入上下文 | ☐ |
| 16 | MCP 客户端：接入外部的 MCP server | 标准化的工具协议 | ☐ |

## 阶段四：工程化与"小龙虾"特性（第 17–21 天）

| 天 | 功能 | 学到什么 | 状态 |
|---|---|---|---|
| 17 | Hooks：工具执行前后运行用户脚本 | 可扩展性 | ☐ |
| 18 | prompt caching 与成本统计 | 实际使用中的成本优化 | ☐ |
| 19 | `rich` 终端界面：diff 展示、Ctrl+C 中断 | 交互体验 | ☐ |
| 20 | 扩充评测集（10+ 个任务），自动跑分并对比 | 量化迭代效果 | ☐ |
| 21 | 常驻模式：定时任务，接入 Telegram 等消息渠道 | 从命令行工具变成长期在线的助手（OpenClaw 的核心） | ☐ |

## 参考资料

- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)：约 100 行实现的编程 agent，对应第 1–5 天的内容
- Anthropic《Building Effective Agents》：https://www.anthropic.com/engineering/building-effective-agents
- Anthropic tool use 文档：https://docs.anthropic.com/en/docs/build-with-claude/tool-use

## 待定事项

- [x] 模型 API：GLM Coding Plan，走 Anthropic Messages 协议；如需切换厂商，第 8 天前再抽象 provider
