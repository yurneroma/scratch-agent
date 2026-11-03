"""Fixed, filesystem-based evaluation tasks for the agent."""

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from . import tools
from .config import Config
from .tools import TOOLS, execute_tool

TASKS_PATH = Path(__file__).resolve().parents[2] / "evals" / "tasks.json"
MAX_EVAL_ITERATIONS = 10


@dataclass(frozen=True)
class EvalTask:
    id: str
    prompt: str
    files: dict[str, str]
    required_tools: list[str]
    checks: dict[str, Any]


@dataclass
class EvalResult:
    task_id: str
    passed: bool
    answer: str
    failures: list[str]
    tool_calls: list[str]
    input_tokens: int
    output_tokens: int
    iterations: int
    stop_reason: str
    error: str | None = None


def load_tasks() -> list[EvalTask]:
    """Load and validate the fixed task definitions."""
    raw = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    tasks = [
        EvalTask(
            id=item["id"],
            prompt=item["prompt"],
            files=item.get("files", {}),
            required_tools=item.get("required_tools", []),
            checks=item.get("checks", {}),
        )
        for item in raw["tasks"]
    ]
    if not tasks:
        raise ValueError("evaluation task set is empty")
    task_ids = [task.id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("evaluation task ids must be unique")
    return tasks


def content_block_dict(block: Any) -> dict[str, Any]:
    """Convert an SDK content block into the dict sent back in messages."""
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump()
    if getattr(block, "type", None) == "text":
        return {"type": "text", "text": block.text}
    if getattr(block, "type", None) == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": dict(block.input),
        }
    raise TypeError(f"unsupported content block: {type(block).__name__}")


def response_text(content_blocks: list[Any]) -> str:
    parts: list[str] = []
    for block in content_blocks:
        block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if block_type != "text":
            continue
        text = block.get("text") if isinstance(block, dict) else block.text
        parts.append(text)
    return "".join(parts)


def write_task_files(root: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        target = (root / relative_path).resolve()
        target.relative_to(root)  # Fail loudly on an invalid packaged task.
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def run_headless_agent(
    client: Anthropic,
    config: Config,
    task: EvalTask,
    root: Path,
) -> tuple[str, list[str], int, int, int, str, str | None]:
    """Run one task without terminal streaming or interactive confirmation."""
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"{task.prompt}\n\n"
                "Work only inside the current workspace. When you are done, "
                "give the requested final answer."
            ),
        }
    ]
    tool_calls: list[str] = []
    input_tokens = 0
    output_tokens = 0
    stop_reason = "unknown"
    answer = ""

    for iteration in range(1, MAX_EVAL_ITERATIONS + 1):
        try:
            response = client.messages.create(
                model=config.model,
                max_tokens=config.max_tokens,
                messages=messages,
                tools=TOOLS,
            )
        except Exception as e:
            return answer, tool_calls, input_tokens, output_tokens, iteration, stop_reason, (
                f"{type(e).__name__}: {e}"
            )

        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens
        stop_reason = response.stop_reason or "unknown"
        serialized_blocks = [content_block_dict(block) for block in response.content]
        answer = response_text(response.content)
        messages.append({"role": "assistant", "content": serialized_blocks})

        if stop_reason != "tool_use":
            return (
                answer,
                tool_calls,
                input_tokens,
                output_tokens,
                iteration,
                stop_reason,
                None,
            )

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            result = execute_tool(
                block.name,
                dict(block.input),
                auto_approve=True,
            )
            tool_calls.append(block.name)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    return (
        answer,
        tool_calls,
        input_tokens,
        output_tokens,
        MAX_EVAL_ITERATIONS,
        stop_reason,
        "maximum evaluation iterations reached",
    )


def grade_task(task: EvalTask, root: Path, answer: str, tool_calls: list[str]) -> list[str]:
    """Grade observable results, not whether the model used a preferred tool."""
    failures: list[str] = []

    for required_tool in task.required_tools:
        if required_tool not in tool_calls:
            failures.append(f"required tool was not used: {required_tool}")

    for expected in task.checks.get("answer_contains", []):
        if expected not in answer:
            failures.append(f"answer does not contain: {expected!r}")

    for relative_path, expected_parts in task.checks.get("file_contains", {}).items():
        target = root / relative_path
        if not target.is_file():
            failures.append(f"missing expected file: {relative_path}")
            continue
        content = target.read_text(encoding="utf-8")
        for expected in expected_parts:
            if expected not in content:
                failures.append(f"{relative_path} does not contain: {expected!r}")

    for relative_path, forbidden_parts in task.checks.get("file_not_contains", {}).items():
        target = root / relative_path
        if not target.is_file():
            continue
        content = target.read_text(encoding="utf-8")
        for forbidden in forbidden_parts:
            if forbidden in content:
                failures.append(f"{relative_path} unexpectedly contains: {forbidden!r}")

    return failures


def run_task(client: Anthropic, config: Config, task: EvalTask) -> EvalResult:
    """Create an isolated workspace, run one task, and grade the result."""
    old_workspace_root = tools.WORKSPACE_ROOT
    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            tools.WORKSPACE_ROOT = root
            write_task_files(root, task.files)

            (
                answer,
                tool_calls,
                input_tokens,
                output_tokens,
                iterations,
                stop_reason,
                error,
            ) = run_headless_agent(client, config, task, root)
            failures = grade_task(task, root, answer, tool_calls)
            if error:
                failures.append(error)

            return EvalResult(
                task_id=task.id,
                passed=not failures,
                answer=answer.strip(),
                failures=failures,
                tool_calls=tool_calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                iterations=iterations,
                stop_reason=stop_reason,
                error=error,
            )
    finally:
        tools.WORKSPACE_ROOT = old_workspace_root


def run_evaluations(
    client: Anthropic,
    config: Config,
    selected_ids: list[str] | None = None,
) -> list[EvalResult]:
    tasks = load_tasks()
    if selected_ids is None:
        selected_tasks = tasks
    else:
        tasks_by_id = {task.id: task for task in tasks}
        unknown = set(selected_ids) - set(tasks_by_id)
        if unknown:
            known = ", ".join(task.id for task in tasks)
            raise SystemExit(f"unknown eval task(s): {', '.join(sorted(unknown))}\nknown: {known}")
        selected_tasks = [tasks_by_id[task_id] for task_id in selected_ids]

    results: list[EvalResult] = []
    for index, task in enumerate(selected_tasks, start=1):
        print(f"[{index}/{len(selected_tasks)}] {task.id}...", flush=True)
        result = run_task(client, config, task)
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(
            f"  {status} | tools={','.join(result.tool_calls) or '-'} "
            f"in={result.input_tokens} out={result.output_tokens}"
        )
        for failure in result.failures:
            print(f"    - {failure}")

    passed = sum(result.passed for result in results)
    print(f"\nEval summary: {passed}/{len(results)} passed")
    return results


def eval_main(
    client: Anthropic,
    config: Config,
    selected_ids: list[str] | None = None,
    output_path: str | None = None,
) -> None:
    results = run_evaluations(client, config, selected_ids)
    if output_path:
        report_path = Path(output_path).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"report: {report_path}")
