"""Model routing: every LLM in the app is built here, by task.

    planner  → Sonnet 5.5   every decision + trip edits (tool loop)
    research → Haiku 4.5    reads many search results, returns a brief
    summary  → Haiku 4.5    tiny jobs (titles, short summaries)
    judge    → Opus 5.5     grades eval runs

Notes for the 5.5 models: no `temperature` (non-default → 400), no forced
`tool_choice` (→ 400), so structured output must use method="json_schema".
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_anthropic import ChatAnthropic

from trip_planner.config import get_settings

Task = Literal["planner", "research", "summary", "judge"]


def _supports_effort(model: str) -> bool:
    return not model.startswith("claude-haiku")


@lru_cache(maxsize=8)
def get_llm(task: Task) -> ChatAnthropic:
    s = get_settings()
    model, effort, max_tokens = {
        "planner": (s.planner_model, s.planner_effort, 16000),
        "research": (s.research_model, None, 4000),
        "summary": (s.summary_model, None, 1000),
        "judge": (s.judge_model, s.judge_effort, 8000),
    }[task]

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "max_retries": 3,
        "timeout": 300,
        # Auto-cache the longest stable prefix (tools + system + history so far).
        "model_kwargs": {"extra_body": {"cache_control": {"type": "ephemeral"}}},
    }
    if s.anthropic_api_key:
        kwargs["api_key"] = s.anthropic_api_key
    if effort and _supports_effort(model):
        kwargs["effort"] = effort
    if task in ("planner", "judge"):
        # Server-side refusal fallback: if a safety classifier declines, the API
        # re-runs the request on a suitable model inside the same call.
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["model_kwargs"]["extra_body"]["fallbacks"] = "default"
    return ChatAnthropic(**kwargs)
