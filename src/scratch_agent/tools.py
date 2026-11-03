"""Tools that the agent can call.

Each tool is a function that takes parsed arguments and returns a result string.
The schema tells the model what tools exist and how to call them.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


# Keep tool output small enough for the model context. Bash will need the same
# protection on Day 5.
MAX_TOOL_OUTPUT_CHARS = 20_000
MAX_GLOB_RESULTS = 200
MAX_GREP_RESULTS = 200

# These directories are useful to humans and editors, but usually waste agent
# context when searching a project.
SKIPPED_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}

WORKSPACE_ROOT = Path.cwd().resolve()


@dataclass(frozen=True)
class Tool:
    """A tool schema plus the Python function implementing it."""

    name: str
    description: str
    input_schema: dict[str, Any]
    function: Callable[..., str]

    def schema(self) -> dict[str, Any]:
        """Return the JSON schema sent to the model."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def truncate_output(text: str) -> str:
    """Cap tool output so one large file or search cannot flood the context."""
    if len(text) <= MAX_TOOL_OUTPUT_CHARS:
        return text
    omitted = len(text) - MAX_TOOL_OUTPUT_CHARS
    return (
        text[:MAX_TOOL_OUTPUT_CHARS]
        + f"\n... [truncated: omitted {omitted} of {len(text)} chars]"
    )


def resolve_workspace_path(path: str) -> Path:
    """Resolve a user/model-provided path and keep it inside the workspace."""
    if not path or not path.strip():
        raise ValueError("path must not be empty")

    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate

    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ValueError(f"path is outside the workspace: {path}") from exc
    return resolved


def in_workspace(path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(WORKSPACE_ROOT)
        return True
    except ValueError:
        return False


def relative_name(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE_ROOT))
    except ValueError:
        return str(path)


def read_file(path: str) -> str:
    """Read a file and return its content."""
    try:
        target = resolve_workspace_path(path)
        if not target.exists():
            return f"Error: file not found: {path}"
        if not target.is_file():
            return f"Error: not a file: {path}"
        return truncate_output(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as e:
        return f"Error reading {path}: {type(e).__name__}: {e}"


def write_file(path: str, content: str) -> str:
    """Create or completely replace a file."""
    try:
        target = resolve_workspace_path(path)
        if target.exists() and target.is_dir():
            return f"Error: path is a directory: {path}"

        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        target.write_text(content, encoding="utf-8")
        line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"Wrote {relative_name(target)} ({len(encoded)} bytes, {line_count} lines)"
    except (OSError, UnicodeError, ValueError) as e:
        return f"Error writing {path}: {type(e).__name__}: {e}"


def edit(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Replace an exact string in a file."""
    try:
        target = resolve_workspace_path(path)
        if not target.exists():
            return f"Error: file not found: {path}"
        if not target.is_file():
            return f"Error: not a file: {path}"
        if not old_string:
            return "Error: old_string must not be empty"
        if old_string == new_string:
            return "Error: old_string and new_string are identical"

        content = target.read_text(encoding="utf-8")
        occurrences = content.count(old_string)
        if occurrences == 0:
            return f"Error: old_string not found in {path}"
        if occurrences > 1 and not replace_all:
            return (
                f"Error: old_string occurs {occurrences} times in {path}. "
                "Make it unique or set replace_all=true."
            )

        updated = content.replace(old_string, new_string)
        target.write_text(updated, encoding="utf-8")
        count = occurrences if replace_all else 1
        return f"Edited {relative_name(target)} ({count} replacement{'s' if count != 1 else ''})"
    except (OSError, UnicodeError, ValueError) as e:
        return f"Error editing {path}: {type(e).__name__}: {e}"


def glob(pattern: str, path: str = ".") -> str:
    """Find files with a shell-style path pattern."""
    try:
        if not pattern:
            return "Error: pattern must not be empty"
        if Path(pattern).is_absolute():
            return "Error: pattern must be relative to path"

        base = resolve_workspace_path(path)
        if not base.exists():
            return f"Error: path not found: {path}"
        if not base.is_dir():
            return f"Error: path is not a directory: {path}"

        matches: list[str] = []
        truncated = False
        for match in base.glob(pattern):
            if not in_workspace(match):
                continue
            if any(part in SKIPPED_DIRS for part in match.parts):
                continue
            if match.is_file():
                matches.append(relative_name(match.resolve(strict=False)))
                if len(matches) >= MAX_GLOB_RESULTS:
                    truncated = True
                    break

        if not matches:
            return "No files matched."
        matches.sort()
        output = "\n".join(matches)
        if truncated:
            output += f"\n... [truncated: stopped after {MAX_GLOB_RESULTS} matches]"
        return truncate_output(output)
    except (OSError, ValueError) as e:
        return f"Error running glob: {type(e).__name__}: {e}"


def grep(pattern: str, path: str = ".", include: str | None = None) -> str:
    """Search file contents with a regular expression."""
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex: {e}"

    try:
        base = resolve_workspace_path(path)
        if not base.exists():
            return f"Error: path not found: {path}"
        if not base.is_file() and not base.is_dir():
            return f"Error: path is neither a file nor a directory: {path}"
        if include is not None and (not include or Path(include).is_absolute()):
            return "Error: include must be a non-empty relative pattern"

        candidates = [base] if base.is_file() else base.rglob(include or "*")
        matches: list[str] = []
        errors: list[str] = []
        truncated = False

        for candidate in candidates:
            if not candidate.is_file():
                continue
            if any(part in SKIPPED_DIRS for part in candidate.parts):
                continue
            if not in_workspace(candidate):
                continue

            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as e:
                if len(errors) < 3:
                    errors.append(
                        f"[unreadable] {relative_name(candidate)}: "
                        f"{type(e).__name__}: {e}"
                    )
                continue

            for line_number, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    matches.append(
                        f"{relative_name(candidate)}:{line_number}:{line.rstrip()}"
                    )
                    if len(matches) >= MAX_GREP_RESULTS:
                        truncated = True
                        break
            if truncated:
                break

        output_parts = matches + errors
        if not output_parts:
            return "No matches."
        output = "\n".join(output_parts)
        if truncated:
            output += f"\n... [truncated: stopped after {MAX_GREP_RESULTS} matches]"
        return truncate_output(output)
    except (OSError, ValueError) as e:
        return f"Error running grep: {type(e).__name__}: {e}"


TOOL_REGISTRY: list[Tool] = [
    Tool(
        name="read_file",
        description=(
            "Read a file when you need its exact content. Output may be truncated "
            "for very large files."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative path to the file",
                }
            },
            "required": ["path"],
        },
        function=read_file,
    ),
    Tool(
        name="write_file",
        description=(
            "Create a new file or completely replace an existing file. "
            "Prefer edit when changing part of an existing file."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative path to the file",
                },
                "content": {
                    "type": "string",
                    "description": "Complete file content to write",
                },
            },
            "required": ["path", "content"],
        },
        function=write_file,
    ),
    Tool(
        name="edit",
        description=(
            "Replace an exact unique string in a file. old_string must match "
            "exactly, including whitespace and indentation. Set replace_all=true "
            "only when every occurrence should change."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative path to the file",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact existing text to replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement text",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace every occurrence instead of requiring a unique match",
                    "default": False,
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
        function=edit,
    ),
    Tool(
        name="glob",
        description=(
            "Find file paths with a shell-style pattern. Use this when the exact "
            "path is unknown, for example '*.py' or 'notes/day*.md'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern such as '*.py' or '**/*.md'",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search from",
                    "default": ".",
                },
            },
            "required": ["pattern"],
        },
        function=glob,
    ),
    Tool(
        name="grep",
        description=(
            "Search file contents with a regular expression and return matching "
            "lines as path:line:text. Use this to find where a symbol, string, "
            "or pattern appears."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Python regular expression to search for",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search",
                    "default": ".",
                },
                "include": {
                    "type": "string",
                    "description": "Optional glob pattern for files to search, such as '*.py'",
                },
            },
            "required": ["pattern"],
        },
        function=grep,
    ),
]


# The API takes plain dictionaries; the registry keeps schemas and functions aligned.
TOOLS = [tool.schema() for tool in TOOL_REGISTRY]
TOOL_FUNCTIONS = {tool.name: tool.function for tool in TOOL_REGISTRY}
