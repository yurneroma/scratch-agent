"""Thin wrapper that builds an Anthropic SDK client pointed at the GLM endpoint."""

from anthropic import Anthropic

from .config import Config


def make_client(config: Config) -> Anthropic:
    # GLM docs authenticate via ANTHROPIC_AUTH_TOKEN, i.e. `Authorization: Bearer <key>`,
    # so pass the key as auth_token rather than api_key (which sends `x-api-key`).
    return Anthropic(auth_token=config.api_key, base_url=config.base_url)
