from __future__ import annotations

from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from config.model_config import AgentModelConfig, get_agent_config
from config.settings import get_settings


def build_llm(config: AgentModelConfig) -> BaseChatModel:
    """Instantiate an LLM from an AgentModelConfig."""
    s = get_settings()
    if config.provider == "anthropic":
        return ChatAnthropic(
            model=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=s.llm.anthropic_api_key,
        )
    return ChatOpenAI(
        model=config.model_name,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        api_key=s.llm.openai_api_key,
    )


@lru_cache(maxsize=16)
def get_llm_for_agent(agent_name: str) -> BaseChatModel:
    """
    Return a cached LLM instance for the named agent.

    The same agent always gets the same model config, so caching is safe.
    Call clear_llm_cache() in tests that need fresh instances.
    """
    return build_llm(get_agent_config(agent_name))


def clear_llm_cache() -> None:
    """Invalidate the LLM instance cache (useful in tests)."""
    get_llm_for_agent.cache_clear()
