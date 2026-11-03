# Day 4: 工具注册表与基础文件工具

## 做了什么

把原来分离的 `TOOLS` schema 列表和 `TOOL_FUNCTIONS` 映射合并成一个工具注册表。每个 `Tool` 同时保存：

- 模型看到的 `name`、`description`、`input_schema`
- Python 侧真正执行的 `function`

这样工具名、schema 和实现不容易脱节。

新增了四个工具：

- `write_file(path, content)`：创建文件或完整覆盖文件
- `edit(path, old_string, new_string, replace_all)`：做精确字符串替换
- `glob(pattern, path)`：按 shell 风格模式查找文件
- `grep(pattern, path, include)`：按正则搜索文件内容

同时给所有文件工具加了两个保护：

1. **Workspace 边界检查**：解析路径后必须位于当前工作目录内，不能通过 `../` 或绝对路径访问项目外文件
2. **输出截断**：单个工具结果最多 20,000 字符，避免大文件或大量搜索结果撑爆上下文

## 学到了什么

**1. 工具描述是给模型的行为提示**

同样的函数能力，描述不同，模型的选择会不同。比如 `write_file` 的描述里明确写了：

> Prefer edit when changing part of an existing file.

这是在引导模型不要为了改一行而重写整个文件。`edit` 的描述则强调 `old_string` 必须精确匹配，包括缩进和空白，因为这是字符串替换工具最常见的失败原因。

**2. schema 的默认值不属于协议本身**

`replace_all` 和 `path` 在 Python 函数里有默认值，但 Anthropic tool schema 里的 `default` 只是描述性信息。真正执行时仍然是 Python 函数根据收到的参数应用默认值。

**3. 破坏性工具需要比只读工具更谨慎**

`edit` 默认要求 `old_string` 在文件中唯一。如果出现多处匹配，工具不会猜模型想改哪一处，而是返回错误，要求提供更长上下文或显式设置 `replace_all=true`。

这比“直接替换第一处”更可靠。对编辑工具来说，宁可让模型重试，也不要默默改错。

**4. 搜索工具的价值是减少上下文消耗**

Day 3 的 `read_file` 只能先知道路径再读文件。现在有了 `glob` 和 `grep`，agent 可以先定位：

```text
glob("notes/day*.md")     → 找到文件路径
grep("chat_loop")         → 找到符号所在文件和行号
read_file("src/...")      → 再读最小必要内容
```

这更接近真实 coding agent 的工作方式：先搜索定位，再读取理解，最后修改验证。

## 验证

添加了 `tests/test_tools.py`，覆盖：

- 注册表里的 schema 和函数名一致
- 路径不能逃出 workspace
- `write_file` / `read_file` / `edit` 的完整闭环
- 多处匹配时 `edit` 拒绝默认替换
- `replace_all=true` 时可以全部替换
- `glob` 和 `grep` 能找到目标并跳过 `.venv` 等依赖目录
- `grep` 支持搜索单个文件
- 大文件输出会被截断

运行：

```bash
uv run python -m unittest discover -s tests -v
```

结果：9 个测试全部通过。
