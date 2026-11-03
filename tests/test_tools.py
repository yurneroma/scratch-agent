import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scratch_agent import tools


class ToolTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name).resolve()
        mock.patch.object(
            tools,
            "WORKSPACE_ROOT",
            self.root,
        ).start()
        self.addCleanup(mock.patch.stopall)

        (self.root / "sample.py").write_text(
            "def hello():\n    return 'hello'\n\ndef goodbye():\n    return 'bye'\n",
            encoding="utf-8",
        )
        (self.root / "notes").mkdir()
        (self.root / "notes" / "day04.md").write_text(
            "# Day 4\n\nTools and registry.\n",
            encoding="utf-8",
        )
        (self.root / ".venv").mkdir()
        (self.root / ".venv" / "ignored.py").write_text(
            "hello = 'ignored'\n",
            encoding="utf-8",
        )

    def test_registry_keeps_schemas_and_functions_aligned(self):
        schema_names = {tool["name"] for tool in tools.TOOLS}
        function_names = set(tools.TOOL_FUNCTIONS)

        self.assertEqual(schema_names, function_names)
        self.assertIn(
            "read_file",
            schema_names,
        )
        self.assertIn("write_file", schema_names)
        self.assertIn("edit", schema_names)
        self.assertIn("glob", schema_names)
        self.assertIn("grep", schema_names)

    def test_paths_cannot_escape_workspace(self):
        with self.assertRaises(ValueError):
            tools.resolve_workspace_path("../outside.txt")

    def test_write_read_and_edit(self):
        write_result = tools.write_file(
            "docs/generated.txt",
            "first\nsecond\n",
        )
        self.assertIn("Wrote docs/generated.txt", write_result)
        self.assertEqual(
            tools.read_file("docs/generated.txt"),
            "first\nsecond\n",
        )

        edit_result = tools.edit(
            "docs/generated.txt",
            "second",
            "changed",
        )
        self.assertIn("Edited docs/generated.txt", edit_result)
        self.assertEqual(
            tools.read_file("docs/generated.txt"),
            "first\nchanged\n",
        )

    def test_edit_rejects_ambiguous_replacement(self):
        result = tools.edit("sample.py", "hello", "hi")

        self.assertIn("occurs 2 times", result)
        self.assertIn("replace_all=true", result)

    def test_edit_can_replace_every_occurrence(self):
        result = tools.edit(
            "sample.py",
            "hello",
            "hi",
            replace_all=True,
        )

        self.assertIn("Edited sample.py (2 replacements)", result)
        self.assertIn("def hi():", tools.read_file("sample.py"))

    def test_glob_finds_files_and_skips_dependency_directories(self):
        result = tools.glob("**/*.py")

        self.assertIn("sample.py", result.splitlines())
        self.assertNotIn(".venv/ignored.py", result)

    def test_grep_returns_line_numbers_and_skips_dependency_directories(self):
        result = tools.grep("hello", include="*.py")

        self.assertIn("sample.py:2:    return 'hello'", result.splitlines())
        self.assertNotIn(".venv/ignored.py", result)

    def test_grep_accepts_a_single_file(self):
        result = tools.grep("goodbye", path="sample.py")

        self.assertIn("sample.py:4:def goodbye():", result.splitlines())

    def test_read_file_truncates_large_output(self):
        tools.write_file("large.txt", "x" * 100)

        with mock.patch.object(tools, "MAX_TOOL_OUTPUT_CHARS", 10):
            result = tools.read_file("large.txt")

        self.assertTrue(result.startswith("x" * 10))
        self.assertIn("[truncated: omitted 90 of 100 chars]", result)


if __name__ == "__main__":
    unittest.main()
