"""Day 3: first tool (read_file) and the agent loop.

The agent loop is the core of every agent:
    while stop_reason == "tool_use":
        execute tools
        send tool_result back
        get next response

When stop_reason is "end_turn", the model has nothing more to do and we're done.
"""

import sys
from typing import Any

from anthropic import Anthropic

from .config import Config
from .tools import TOOLS, execute_tool

EXIT_COMMANDS = {"/exit", "/quit"}


def text_of(content) -> str:
    """Join the text blocks of an assistant reply, skipping other block types (e.g. thinking)."""
    return "".join(block.text for block in content if block.type == "text")


def confirm_tool(tool_name: str, tool_input: dict[str, Any]) -> bool:
    """Ask before running tools whose policy requires user confirmation."""
    print(f"\n⚠️  {tool_name} wants to run:")
    if tool_name == "bash":
        print(tool_input.get("command", ""))
    else:
        print(tool_input)

    try:
        answer = input("Allow this command? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes"}


def print_stream(stream) -> tuple[list[dict[str, Any]], str, dict[str, int]]:
    """
    Print the stream as it arrives and return (content_blocks, stop_reason, usage).

    Streaming sends deltas: content_block_start, content_block_delta, content_block_stop.
    We reconstruct the final content blocks from these deltas.
    """
    content_blocks: list[dict[str, Any]] = []
    stop_reason = "unknown"
    usage = {"input_tokens": 0, "output_tokens": 0}

    for event in stream:
        match event.type:
            case "message_start":
                usage["input_tokens"] = event.message.usage.input_tokens
            case "content_block_start":
                block_type = event.content_block.type
                content_blocks.append({"type": block_type})
                match block_type:
                    case "text":
                        content_blocks[-1]["text"] = ""
                    case "thinking":
                        content_blocks[-1]["thinking"] = ""
                        print("💭 ", end="", flush=True)
                    case "tool_use":
                        # tool_use block has: id, name, input (input arrives as deltas)
                        content_blocks[-1]["id"] = event.content_block.id
                        content_blocks[-1]["name"] = event.content_block.name
                        content_blocks[-1]["input"] = {}
            case "content_block_delta":
                delta = event.delta
                match delta.type:
                    case "text_delta":
                        content_blocks[-1]["text"] += delta.text
                        print(delta.text, end="", flush=True)
                    case "thinking_delta":
                        content_blocks[-1]["thinking"] += delta.thinking
                        print(delta.thinking, end="", flush=True)
                    case "input_json_delta":
                        # input_json_delta sends raw JSON string fragments.
                        # We'll parse the complete JSON after the block stops.
                        if "input_json" not in content_blocks[-1]:
                            content_blocks[-1]["input_json"] = ""
                        content_blocks[-1]["input_json"] += delta.partial_json
            case "content_block_stop":
                if content_blocks[-1]["type"] == "thinking":
                    print()  # newline after thinking block
                elif content_blocks[-1]["type"] == "tool_use":
                    # Parse the accumulated JSON string into the input dict
                    import json
                    json_str = content_blocks[-1].pop("input_json", "{}")
                    content_blocks[-1]["input"] = json.loads(json_str)
                    tool_name = content_blocks[-1]["name"]
                    print(f"🔧 {tool_name}({content_blocks[-1]['input']})")
            case "message_delta":
                stop_reason = event.delta.stop_reason
                usage["output_tokens"] = event.usage.output_tokens
            case "message_stop":
                pass

    print()  # final newline after the whole message
    return content_blocks, stop_reason, usage


def chat_loop(client: Anthropic, config: Config) -> None:
    messages: list[dict] = []
    print(f"scratch-agent ({config.model}). /exit or Ctrl+D to quit, /clear to reset history.")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not user_input:
            continue
        if user_input in EXIT_COMMANDS:
            return
        if user_input == "/clear":
            messages.clear()
            print("(history cleared)")
            continue

        messages.append({"role": "user", "content": user_input})

        # Agent loop: keep going while the model wants to use tools.
        total_usage = {"input_tokens": 0, "output_tokens": 0}
        iteration = 0
        max_iterations = 10  # prevent infinite loops

        while iteration < max_iterations:
            iteration += 1
            try:
                with client.messages.stream(
                    model=config.model,
                    max_tokens=config.max_tokens,
                    messages=messages,
                    tools=TOOLS,
                ) as stream:
                    content_blocks, stop_reason, usage = print_stream(stream)
            except Exception as e:
                if iteration == 1:
                    messages.pop()  # drop the user turn if first iteration fails
                print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)
                break

            total_usage["input_tokens"] += usage["input_tokens"]
            total_usage["output_tokens"] += usage["output_tokens"]

            # Add the assistant's response to history
            messages.append({"role": "assistant", "content": content_blocks})

            if stop_reason == "end_turn":
                # Model is done, no more tools to call
                break
            elif stop_reason == "tool_use":
                # Execute all tool_use blocks and send results back
                tool_results = []
                for block in content_blocks:
                    if block["type"] == "tool_use":
                        tool_name = block["name"]
                        tool_input = block["input"]
                        tool_id = block["id"]

                        result = execute_tool(
                            tool_name,
                            tool_input,
                            confirm=confirm_tool,
                        )

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": result,
                        })
                        print(f"  → {len(result)} chars")

                # Send tool results back to the model
                messages.append({"role": "user", "content": tool_results})
            elif stop_reason == "max_tokens":
                print("[warning] hit max_tokens, response truncated")
                break
            else:
                print(f"[warning] unexpected stop_reason: {stop_reason}")
                break

        if iteration >= max_iterations:
            print(f"[warning] hit max_iterations ({max_iterations}), stopping")

        print(
            f"[{stop_reason} | in={total_usage['input_tokens']} "
            f"out={total_usage['output_tokens']} | turns={len([m for m in messages if m['role'] == 'user' and isinstance(m['content'], str)])}]"
        )
