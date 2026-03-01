from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from config.settings import get_settings

Provider = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class AgentModelConfig:
    model_name: str
    temperature: float
    max_tokens: int
    provider: Provider = "openai"


def _s() -> object:
    return get_settings()


# ---------------------------------------------------------------------------
# Registry — maps agent name → model config
# Override model_name by changing SUPERVISOR_MODEL / FAST_MODEL env vars.
# ---------------------------------------------------------------------------
def get_model_registry() -> dict[str, AgentModelConfig]:
    s = get_settings()
    supervisor = s.llm.supervisor_model
    fast = s.llm.fast_model
    validator = s.llm.validator_model

    def _provider(name: str) -> Provider:
        return "anthropic" if "claude" in name.lower() else "openai"

    return {
        "supervisor": AgentModelConfig(
            model_name=supervisor,
            temperature=0.3,
            max_tokens=2048,
            provider=_provider(supervisor),
        ),
        "research": AgentModelConfig(
            model_name=fast,
            temperature=0.5,
            max_tokens=4096,
            provider=_provider(fast),
        ),
        "flights": AgentModelConfig(
            model_name=fast,
            temperature=0.1,
            max_tokens=2048,
            provider=_provider(fast),
        ),
        "hotels": AgentModelConfig(
            model_name=fast,
            temperature=0.1,
            max_tokens=2048,
            provider=_provider(fast),
        ),
        "experiences": AgentModelConfig(
            model_name=fast,
            temperature=0.6,
            max_tokens=3072,
            provider=_provider(fast),
        ),
        "budget": AgentModelConfig(
            model_name=fast,
            temperature=0.1,
            max_tokens=2048,
            provider=_provider(fast),
        ),
        "itinerary": AgentModelConfig(
            model_name=supervisor,
            temperature=0.7,
            max_tokens=8192,
            provider=_provider(supervisor),
        ),
        "validator": AgentModelConfig(
            model_name=validator,
            temperature=0.0,
            max_tokens=1024,
            provider=_provider(validator),
        ),
        "booking": AgentModelConfig(
            model_name=fast,
            temperature=0.0,
            max_tokens=1024,
            provider=_provider(fast),
        ),
        "memory": AgentModelConfig(
            model_name=fast,
            temperature=0.0,
            max_tokens=512,
            provider=_provider(fast),
        ),
    }


def get_agent_config(agent_name: str) -> AgentModelConfig:
    registry = get_model_registry()
    if agent_name not in registry:
        raise KeyError(f"Unknown agent: {agent_name!r}. Known: {list(registry)}")
    return registry[agent_name]
