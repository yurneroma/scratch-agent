"""Configuration loaded from environment variables (and an optional .env file)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# GLM Coding Plan, Anthropic Messages protocol endpoint.
# See https://docs.bigmodel.cn/cn/coding-plan/quick-start
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/anthropic"
DEFAULT_MODEL = "glm-5.3"
DEFAULT_MAX_TOKENS = 8192


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    model: str
    max_tokens: int


def load_config() -> Config:
    load_dotenv()
    api_key = os.environ.get("GLM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GLM_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return Config(
        api_key=api_key,
        base_url=os.environ.get("GLM_BASE_URL", DEFAULT_BASE_URL),
        model=os.environ.get("GLM_MODEL", DEFAULT_MODEL),
        max_tokens=int(os.environ.get("GLM_MAX_TOKENS", DEFAULT_MAX_TOKENS)),
    )
