from __future__ import annotations

from importlib import import_module
from typing import Any

from config.settings import get_settings

_cache: dict[str, Any] = {}


def load_prompts() -> Any:
    """Load prompt module for the configured PROMPT_VERSION."""
    version = get_settings().llm.prompt_version
    if version not in _cache:
        module_path = f"prompts.{version}.all_prompts"
        try:
            _cache[version] = import_module(module_path)
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"Prompt version '{version}' not found at {module_path}"
            ) from exc
    return _cache[version]


def get_prompt(agent_name: str) -> str:
    """Get system prompt string for a named agent."""
    prompts = load_prompts()
    attr = f"{agent_name.upper()}_SYSTEM_PROMPT"
    if not hasattr(prompts, attr):
        raise AttributeError(
            f"Prompt '{attr}' not found in version '{get_settings().llm.prompt_version}'"
        )
    return getattr(prompts, attr)
