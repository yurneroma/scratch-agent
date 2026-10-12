"""scratch-agent entry point.

`scratch-agent`         start the chat loop
`scratch-agent --ping`  send one request to verify the API key and endpoint
"""

import sys

from .chat import chat_loop, text_of
from .config import load_config
from .llm import make_client


def ping() -> None:
    config = load_config()
    client = make_client(config)
    response = client.messages.create(
        model=config.model,
        max_tokens=64,
        messages=[{"role": "user", "content": "Reply with exactly: pong"}],
    )
    print(f"model={response.model} stop_reason={response.stop_reason}")
    print(f"usage: in={response.usage.input_tokens} out={response.usage.output_tokens}")
    print(f"blocks: {[block.type for block in response.content]}")
    print(f"reply: {text_of(response.content)}")


def main() -> None:
    if "--ping" in sys.argv[1:]:
        ping()
        return
    config = load_config()
    chat_loop(make_client(config), config)
