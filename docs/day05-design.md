# Day 5 设计：Bash 工具与固定评测

## 1. 问题定义

Day 4 的 agent 已经能搜索、读取、创建和编辑文件，但它还缺少关键能力：

```text
修改代码之后，自己运行验证
```

没有执行能力时，agent 只能“推测”修改正确；有执行能力后，agent 可以形成闭环：

```text
定位 → 读取 → 修改 → 运行 → 根据错误继续修改 → 汇报
```

Day 5 要解决两个问题：

1. 给 agent 一个可控制的 `bash` 工具
2. 建立固定评测，之后判断功能变化是改进还是退化

## 2. 目标和非目标

### 目标

- 能在 workspace 中执行非交互 shell 命令
- 命令超时后杀掉整个进程组，避免子进程残留
- stdout/stderr/exit code/duration 都返回给模型
- 限制输出大小，避免长输出污染上下文
- 移除明显的密钥环境变量，降低误输出概率
- 普通 chat 中执行 bash 前必须人工确认
- 固定 5 个评测任务，在临时 workspace 中运行
- 评测报告记录通过率、工具调用、token 用量和迭代次数

### 非目标

Day 5 不实现完整权限系统，也不声称 bash 是安全沙箱。

原因很直接：文件工具可以通过路径解析限制访问范围，但 shell 命令天然可以绕过这层限制，例如：

```bash
cat ../outside.txt
```

因此 Day 5 只提供最小安全闸：交互模式下默认询问用户。真正的 allowlist、always-allow、deny 规则和权限状态持久化留给 Day 6。

## 3. 总体架构

```text
                    ┌────────────────────┐
                    │       CLI          │
                    │ scratch-agent      │
                    └─────────┬──────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
      ┌───────────────┐              ┌────────────────┐
      │  chat_loop    │              │ evaluation CLI │
      │  streaming    │              │ non-streaming  │
      └───────┬───────┘              └────────┬───────┘
              │                               │
              │         Anthropic             │
              └───────────────┬───────────────┘
                              │ tool_use
                              ▼
                      ┌───────────────┐
                      │ execute_tool  │
                      └───────┬───────┘
                              │
                              ▼
                      ┌───────────────┐
                      │ tool registry │
                      └───────┬───────┘
                              │
          ┌──────────┬────────┴────────┬─────────────┐
          ▼          ▼                 ▼             ▼
      read_file  write_file/edit   glob/grep       bash
```

交互模式和评测模式共享同一个工具注册表与执行入口：

```python
execute_tool(tool_name, tool_input, ...)
```

这样评测的不是一套特殊工具，而是 agent 真实使用的工具。

## 4. Bash 工具设计

### 4.1 执行生命周期

```text
validate command/timeout
        │
        ▼
copy + sanitize environment
        │
        ▼
Popen(shell=True, cwd=WORKSPACE_ROOT, start_new_session=True)
        │
        ▼
communicate(timeout=timeout)
        │
        ├── 正常结束 → 收集 stdout/stderr/exit_code/duration
        │
        └── TimeoutExpired
                │
                ▼
            os.killpg(process.pid, SIGKILL)
                │
                ▼
            communicate() 收尸
                │
                ▼
            返回 timeout error + partial output
```

### 4.2 为什么使用 process group

命令可能是：

```bash
pytest tests &
sh -c 'sleep 100'
```

如果只杀直接子进程，它派生出的子孙进程可能继续运行。`start_new_session=True` 让 bash 和它的子进程进入同一个进程组；超时后 `os.killpg(..., SIGKILL)` 可以把整组进程杀掉。

### 4.3 超时策略

- 默认：10 秒
- 最大：30 秒
- 小于等于 0：拒绝执行
- 非数字：拒绝执行

超时不是异常崩溃，而是工具结果。模型会看到：

```text
Error: command timed out after 10s and the process group was killed
```

这样它可以选择换命令、缩短范围，或向用户说明任务无法完成。

### 4.4 输出预算

Bash 输出分为三部分：

| 部分 | 预算 |
|---|---:|
| stdout | 14,000 字符 |
| stderr | 4,000 字符 |
| 总返回值 | 20,000 字符 |

截断时保留明确标记：

```text
... [truncated: omitted 1234 of 56789 chars]
```

这不是为了隐藏信息，而是为了防止一次 `cat`、`find` 或测试输出把上下文挤爆。

### 4.5 环境变量

子进程环境来自当前进程，但会移除名称中包含以下标记的变量：

```text
KEY
TOKEN
SECRET
PASSWORD
```

同时移除可能导致额外启动代码的变量：

```text
BASH_ENV
ENV
PYTHONSTARTUP
NODE_OPTIONS
ZDOTDIR
```

这个设计只降低误读环境变量的概率，不是完整安全边界。模型仍可能读取项目里的 `.env` 文件，所以 bash 仍需要用户确认。

## 5. 最小权限闸

`Tool` 增加：

```python
requires_confirmation: bool = False
```

当前只有 `bash` 设为 `True`。

交互模式：

```text
⚠️  bash wants to run:
python test.py
Allow this command? [y/N]
```

用户拒绝时，工具返回：

```text
Error: permission denied for bash
```

这个错误会交还给模型，让它能调整方案或停止。

评测模式使用 `auto_approve=True`：

```text
临时 workspace + 固定任务 + 自动允许 bash
```

因此评测可以无人值守运行，同时不会影响真实交互模式的安全策略。

## 6. 评测系统设计

### 6.1 任务来源

固定任务定义在：

```text
evals/tasks.json
```

当前 5 个任务：

| ID | 能力 |
|---|---|
| `fix-add-function` | 读取并修复简单函数 |
| `locate-symbol` | `grep` 定位文件和行号 |
| `precise-edit` | 多处相似文本中的精确修改 |
| `create-greeting-module` | 从零创建小模块 |
| `run-check-and-fix` | 运行检查、根据失败修复代码 |

### 6.2 隔离执行

每个任务都会创建一个新的临时目录：

```text
temp workspace
    ├── 写入 fixture files
    ├── 临时替换 tools.WORKSPACE_ROOT
    ├── 运行 agent loop
    └── 只对这个目录做 grading
```

评测不会修改当前仓库。

### 6.3 Headless agent loop

评测使用非流式 Messages API：

```text
messages.create
    ↓
end_turn → grade
tool_use → execute_tool(auto_approve=True)
    ↓
tool_result → messages.create
``+

与 chat 模式的差异：

| 模式 | API | 权限 | 输出 |
|---|---|---|---|
| chat | streaming | 用户确认 | 实时打印 |
| eval | non-streaming | 自动允许 | 汇总报告 |

两者共享 `TOOLS`、`TOOL_LOOKUP` 和 `execute_tool`。

### 6.4 Grading 原则

评测只看可观察结果：

- 最终回答是否包含要求的信息
- 文件是否存在
- 文件内容是否包含/不包含指定片段
- 必需工具是否实际使用

不检查“是否按开发者预想的步骤走”。只要结果正确，路径可以不同；如果必需能力没有触发，则算失败。

### 6.5 当前基线

2026-11-03 使用 GLM 跑完整任务集：

```text
5/5 passed
total input tokens: 1,639
total output tokens: 691
tool calls: 14
agent iterations: 17
```

这是一次基线记录，不是稳定常态。模型输出具有随机性，后续功能变化应该用多次运行或固定 seed/采样策略对比。

## 7. CLI 契约

列出任务：

```bash
uv run scratch-agent --eval-list
```

运行全部：

```bash
uv run scratch-agent --eval
```

运行子集：

```bash
uv run scratch-agent --eval-task fix-add-function,locate-symbol
```

写 JSON 报告：

```bash
uv run scratch-agent --eval --eval-output /tmp/scratch-agent-eval.json
```

## 8. 主要风险

| 风险 | 当前处理 | 后续 |
|---|---|---|
| bash 访问 workspace 外文件 | 交互前确认 | Day 6 权限系统 |
| 恶意命令 | 用户可以看到完整命令 | Day 6 规则匹配 |
| 长时间命令 | 默认 10s，最大 30s，杀进程组 | 可配置策略 |
| 长输出 | stdout/stderr/总输出截断 | Day 9 上下文压缩 |
| 密钥泄漏 | 清理常见 secret 环境变量 | 更严格的最小环境 |
| API 失败 | 记录任务失败 | Day 8 重试 |

## 9. 验证

单元测试覆盖：

- bash stdout/stderr/exit code/duration
- timeout 后杀进程组
- secret 环境变量清理
- stdout/stderr 截断
- bash 需要确认
- 用户拒绝后返回 permission denied
- 评测自动允许
- 评测任务数量和 ID 唯一性
- isolated workspace
- answer/file/required-tool grading

运行：

```bash
uv run python -m unittest discover -s tests -v
```
