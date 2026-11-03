"""scratch-agent entry point.

`scratch-agent`         start the chat loop
`scratch-agent --ping`  send one request to verify the API key and endpoint
"""

import argparse

from .chat import chat_loop, text_of
from .config import load_config
from .evals import eval_main, load_tasks
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
    parser = argparse.ArgumentParser(description="A small coding agent built from scratch")
    parser.add_argument("--ping", action="store_true", help="send one request to verify the API setup")
    parser.add_argument("--eval", action="store_true", help="run the fixed evaluation tasks")
    parser.add_argument("--eval-task", help="run one comma-separated subset of evaluation tasks")
    parser.add_argument("--eval-list", action="store_true", help="list evaluation task ids")
    parser.add_argument("--eval-output", help="write a JSON evaluation report to this path")
    args = parser.parse_args()

    if args.ping:
        ping()
        return

    if args.eval_list:
        for task in load_tasks():
            print(task.id)
        return

    config = load_config()
    client = make_client(config)

    if args.eval or args.eval_task:
        selected_ids = None
        if args.eval_task:
            selected_ids = [item.strip() for item in args.eval_task.split(",") if item.strip()]
        eval_main(client, config, selected_ids, args.eval_output)
        return

    chat_loop(client, config)
