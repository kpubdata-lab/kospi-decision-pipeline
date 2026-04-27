from __future__ import annotations

from collections.abc import Mapping


SOURCE_API_KEY_ENV_VARS: dict[str, str] = {
    "ecos": "KPUBDATA_BOK_API_KEY",
    "kosis": "KPUBDATA_KOSIS_API_KEY",
}


def resolve_live_api_key(
    *, source: str, api_key: str | None, environment: Mapping[str, str]
) -> str | None:
    explicit = (api_key or "").strip()
    if explicit:
        return explicit

    env_var_name = SOURCE_API_KEY_ENV_VARS.get(source)
    if env_var_name is None:
        return None

    from_environment = environment.get(env_var_name, "").strip()
    if from_environment:
        return from_environment

    source_name = source.upper()
    raise ValueError(f"{source_name} API key is required via {env_var_name}")
