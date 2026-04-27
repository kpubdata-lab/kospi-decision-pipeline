from __future__ import annotations

import os

import click
from kpubdata import Client

REQUIRED_PROVIDERS: tuple[str, ...] = ("bok", "kosis")


def _env_var_name(provider: str) -> str:
    return f"KPUBDATA_{provider.upper()}_API_KEY"


def _missing_providers() -> list[str]:
    missing: list[str] = []
    for provider in REQUIRED_PROVIDERS:
        if not os.environ.get(_env_var_name(provider)):
            missing.append(provider)
    return missing


def build_client() -> Client:
    missing = _missing_providers()
    if missing:
        expected = ", ".join(_env_var_name(provider) for provider in missing)
        message = (
            f"Missing kpubdata API key(s) for: {', '.join(missing)}."
            f" Set the following environment variable(s): {expected}."
        )
        raise click.ClickException(message)
    return Client.from_env()


__all__ = ["REQUIRED_PROVIDERS", "build_client"]
