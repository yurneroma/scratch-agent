import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scratch_agent.config import Config
from scratch_agent.evals import (
    EvalTask,
    grade_task,
    load_tasks,
    response_text,
    run_task,
)


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeTextBlock:
    type: str
    text: str


@dataclass
class FakeToolUseBlock:
    type: str
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class FakeResponse:
    content: list[Any]
    stop_reason: str
    usage: FakeUsage


class FakeClient:
    def __init__(self):
        self.responses = [
            FakeResponse(
                content=[
                    FakeToolUseBlock(
                        type="tool_use",
                        id="toolu_test",
                        name="bash",
                        input={"command": "printf ok > result.txt"},
                    )
                ],
                stop_reason="tool_use",
                usage=FakeUsage(10, 5),
            ),
            FakeResponse(
                content=[FakeTextBlock(type="text", text="done")],
                stop_reason="end_turn",
                usage=FakeUsage(20, 7),
            ),
        ]
        class Messages:
            def __init__(self, responses):
                self.calls = []
                self.responses = responses

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return self.responses.pop(0)

        self.messages = Messages(self.responses)


class EvaluationTests(unittest.TestCase):
    def test_task_set_is_fixed_and_unique(self):
        tasks = load_tasks()
        ids = [task.id for task in tasks]

        self.assertEqual(len(tasks), 5)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("fix-add-function", ids)
        self.assertIn("run-check-and-fix", ids)

    def test_response_text_accepts_objects_and_dicts(self):
        object_text = response_text([FakeTextBlock(type="text", text="a")])
        dict_text = response_text([{"type": "text", "text": "b"}])

        self.assertEqual(object_text, "a")
        self.assertEqual(dict_text, "b")

    def test_grade_task_checks_answer_files_and_required_tools(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "answer.txt").write_text("result", encoding="utf-8")
            task = EvalTask(
                id="test",
                prompt="test",
                files={},
                required_tools=["bash"],
                checks={
                    "answer_contains": ["result"],
                    "file_contains": {"answer.txt": ["result"]},
                    "file_not_contains": {"answer.txt": ["forbidden"]},
                },
            )

            failures = grade_task(task, root, "result", ["bash"])

        self.assertEqual(failures, [])

    def test_run_task_uses_isolated_workspace_and_auto_approves_tools(self):
        client = FakeClient()
        config = Config(
            api_key="test-key",
            base_url="https://example.invalid",
            model="test-model",
            max_tokens=128,
        )
        task = EvalTask(
            id="test",
            prompt="Use bash, create result.txt with ok, then say done.",
            files={},
            required_tools=["bash"],
            checks={
                "answer_contains": ["done"],
                "file_contains": {"result.txt": ["ok"]},
            },
        )

        result = run_task(client, config, task)

        self.assertTrue(result.passed, result.failures)
        self.assertEqual(result.answer, "done")
        self.assertEqual(result.tool_calls, ["bash"])
        self.assertEqual(result.input_tokens, 30)
        self.assertEqual(result.output_tokens, 12)
        self.assertEqual(result.stop_reason, "end_turn")


if __name__ == "__main__":
    unittest.main()
