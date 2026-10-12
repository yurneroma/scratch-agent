"""Day 1: multi-turn chat in the terminal.

The model is stateless. Each request resends the whole `messages` list,
and that list is the only "memory" the conversation has.
"""

from anthropic import Anthropic

from .config import Config

EXIT_COMMANDS = {"/exit", "/quit"}


def text_of(content) -> str:
    """Join the text blocks of an assistant reply, skipping other block types (e.g. thinking)."""
    return "".join(block.text for block in content if block.type == "text")


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
            response = client.messages.create(
                model=config.model,
                max_tokens=config.max_tokens,
                messages=messages,
            )
        except Exception as e:
            # Drop the unanswered user turn so the history stays user/assistant alternating.
            messages.pop()
            print(f"[error] {type(e).__name__}: {e}")
            continue

        # Store the full content blocks, not just the text: from Day 3 on,
        # tool_use blocks must be sent back exactly as the model produced them.
        messages.append({"role": "assistant", "content": response.content})
        print(text_of(response.content))
        print(
            f"[{response.stop_reason} | in={response.usage.input_tokens} "
            f"out={response.usage.output_tokens} | turns={len(messages) // 2}]"
        )
