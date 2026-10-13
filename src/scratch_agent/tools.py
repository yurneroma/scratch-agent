"""Tools that the agent can call.

Each tool is a function that takes parsed arguments and returns a result string.
The schema tells the model what tools exist and how to call them.
"""

from pathlib import Path


def read_file(path: str) -> str:
    """Read a file and return its content."""
    try:
        content = Path(path).read_text()
        return content
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except Exception as e:
        return f"Error reading {path}: {type(e).__name__}: {e}"


# Tool schemas in Anthropic's format.
# See https://docs.anthropic.com/en/docs/build-with-claude/tool-use
TOOLS = [
    {
        "name": "read_file",
        "description": "Read the full content of a file. Use this when the user asks about a file or you need to see code/docs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                }
            },
            "required": ["path"],
        },
    }
]


# Registry mapping tool names to their implementation functions.
TOOL_FUNCTIONS = {
    "read_file": read_file,
}
