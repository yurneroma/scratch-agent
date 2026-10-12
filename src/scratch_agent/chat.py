"""Day 2: streaming output.

Streaming events arrive one by one. We reconstruct the full content blocks
from the deltas and store them in `messages` at the end.
"""

import sys
from typing import Any

from anthropic import Anthropic

from .config import Config

EXIT_COMMANDS = {"/exit", "/quit"}


def text_of(content) -> str:
    """Join the text blocks of an assistant reply, skipping other block types (e.g. thinking)."""
    return "".join(block.text for block in content if block.type == "text")


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
                content_blocks.append({"type": event.content_block.type})
                match event.content_block.type:
                    case "text":
                        content_blocks[-1]["text"] = ""
                    case "thinking":
                        content_blocks[-1]["thinking"] = ""
                        print("💭 ", end="", flush=True)
            case "content_block_delta":
                delta = event.delta
                match delta.type:
                    case "text_delta":
                        content_blocks[-1]["text"] += delta.text
                        print(delta.text, end="", flush=True)
                    case "thinking_delta":
                        content_blocks[-1]["thinking"] += delta.thinking
                        print(delta.thinking, end="", flush=True)
            case "content_block_stop":
                if content_blocks[-1]["type"] == "thinking":
                    print()  # newline after thinking block
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
        try:
            with client.messages.stream(
                model=config.model,
                max_tokens=config.max_tokens,
                messages=messages,
            ) as stream:
                content_blocks, stop_reason, usage = print_stream(stream)
        except Exception as e:
            messages.pop()
            print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)
            continue

        messages.append({"role": "assistant", "content": content_blocks})
        print(
            f"[{stop_reason} | in={usage['input_tokens']} "
            f"out={usage['output_tokens']} | turns={len(messages) // 2}]"
        )
