"""Model routing: every LLM in the app is built here, by task.

LLM_PROVIDER picks the provider (default openai); each task has a default model and
reasoning effort per provider, overridable with PLANNER_MODEL / PLANNER_EFFORT etc.

    task       openai              anthropic
    planner    gpt-5.5 · medium    claude-sonnet-5-5 · medium   every decision + trip edits
    research   gpt-5.4-mini · low  claude-haiku-4-5             reads search results → brief
    judge      gpt-5.5 · high      claude-opus-5-5 · high       grades eval runs

OpenAI: function tools + reasoning effort require the Responses API.
Anthropic 5.5 models: no `temperature`, no forced `tool_choice`; structured output
must use method="json_schema".
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage

from trip_planner.config import get_settings

Task = Literal["planner", "research", "judge"]

DEFAULTS: dict[str, dict[str, tuple[str, str | None]]] = {
    "openai": {
        "planner": ("gpt-5.5", "medium"),
        "research": ("gpt-5.4-mini", "low"),
        "judge": ("gpt-5.5", "high"),
    },
    "anthropic": {
        "planner": ("claude-sonnet-5-5", "medium"),
        "research": ("claude-haiku-4-5", None),  # Haiku 4.5 has no effort setting
        "judge": ("claude-opus-5-5", "high"),
    },
}
MAX_TOKENS = {"planner": 16000, "research": 4000, "judge": 8000}


def model_for(task: Task) -> tuple[str, str | None]:
    s = get_settings()
    model, effort = DEFAULTS[s.llm_provider][task]
    return getattr(s, f"{task}_model") or model, getattr(s, f"{task}_effort") or effort


@lru_cache(maxsize=8)
def get_llm(task: Task) -> BaseChatModel:
    s = get_settings()
    model, effort = model_for(task)
    common = {"model": model, "max_tokens": MAX_TOKENS[task], "max_retries": 3, "timeout": 300}

    if s.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            **common,
            api_key=s.openai_api_key or None,
            use_responses_api=True,  # tools + reasoning effort aren't allowed on chat completions
            reasoning={"effort": effort} if effort else None,
        )

    from langchain_anthropic import ChatAnthropic

    kwargs: dict = {
        **common,
        # Auto-cache the longest stable prefix (tools + system + history so far).
        "model_kwargs": {"extra_body": {"cache_control": {"type": "ephemeral"}}},
    }
    if s.anthropic_api_key:
        kwargs["api_key"] = s.anthropic_api_key
    if effort:
        kwargs["effort"] = effort
    if task in ("planner", "judge"):
        # Server-side refusal fallback: if a safety classifier declines, the API
        # re-runs the request on a suitable model inside the same call.
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["model_kwargs"]["extra_body"]["fallbacks"] = "default"
    return ChatAnthropic(**kwargs)


def system_message(text: str) -> SystemMessage:
    """Anthropic needs an explicit cache breakpoint; OpenAI caches long prefixes itself."""
    if get_settings().llm_provider == "anthropic":
        return SystemMessage(
            content=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
        )
    return SystemMessage(content=text)
