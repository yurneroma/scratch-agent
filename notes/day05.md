# Day 5: Bash 工具与固定评测

## 做了什么

1. 新增 `bash(command, timeout)` 工具
2. 给 `Tool` 注册表增加 `requires_confirmation`
3. 交互模式下，bash 执行前必须用户确认
4. 评测模式下自动允许 bash，在临时 workspace 中运行
5. 新增 5 个固定评测任务
6. 新增 `--eval`、`--eval-list`、`--eval-task`、`--eval-output`
7. 写了 Day 5 架构与设计细节文档：`docs/day05-design.md`

## 学到了什么

**1. Bash 是能力边界的质变**

Day 4 的 workspace 路径检查能约束文件工具，但约束不了 shell。只要能执行命令，agent 就可以访问文件系统中当前进程有权限访问的大部分资源。

所以 bash 的安全策略不能只靠路径检查，必须有用户确认。完整权限系统留给 Day 6，但最小确认闸必须和 bash 同天出现。

**2. 超时要杀进程组，不只是杀子进程**

`Popen` 创建的是直接子进程，但 shell 命令可能继续派生进程。使用：

```python
start_new_session=True
os.killpg(process.pid, signal.SIGKILL)
```

才能把同一条命令启动的整组进程杀掉。

**3. 工具输出必须预算化**

测试命令很容易产生几万行输出。如果不截断，工具结果会迅速占据上下文，导致 agent 忘记原始任务或成本暴涨。

Bash 使用三层预算：

- stdout 14,000 字符
- stderr 4,000 字符
- 总输出 20,000 字符

**4. 评测要检查结果，不要检查“内心戏”**

评测只判断：

- 最终回答是否满足要求
- 文件结果是否正确
- 必需工具是否真的用过

不要求模型使用完全相同的步骤。这样评测衡量的是任务完成度，不是一次偶然的实现路径。

**5. 交互模式和评测模式共享工具入口**

两种模式都走：

```python
execute_tool(...)
```

差别只在权限：

- chat：用户确认
- eval：临时 workspace + auto approve

这样评测结果更能代表真实 agent 行为。

## 使用

```bash
# 列出任务
uv run scratch-agent --eval-list

# 运行全部评测
uv run scratch-agent --eval

# 运行子集
uv run scratch-agent --eval-task fix-add-function,locate-symbol

# 输出 JSON 报告
uv run scratch-agent --eval --eval-output /tmp/scratch-agent-eval.json
```

## 验证

```bash
uv run python -m unittest discover -s tests -v
```

结果：20 个测试全部通过。

真实 GLM 评测：

```text
uv run scratch-agent --eval

Eval summary: 5/5 passed
```
