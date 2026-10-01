import pytest

from trip_planner import llm
from trip_planner.config import get_settings


@pytest.fixture
def provider(monkeypatch):
    def use(name: str, **env: str):
        monkeypatch.setenv("LLM_PROVIDER", name)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        llm.get_llm.cache_clear()

    yield use
    get_settings.cache_clear()
    llm.get_llm.cache_clear()


def test_openai_routing(provider):
    provider("openai", OPENAI_API_KEY="sk-test", PLANNER_MODEL="", RESEARCH_MODEL="")
    planner = llm.get_llm("planner")
    assert (planner.model_name, planner.reasoning) == ("gpt-5.5", {"effort": "medium"})
    assert planner.use_responses_api  # tools + reasoning effort need the Responses API
    assert llm.get_llm("research").model_name == "gpt-5.4-mini"
    assert llm.model_for("judge") == ("gpt-5.5", "high")
    assert isinstance(llm.system_message("x").content, str)


def test_env_overrides_model_and_effort(provider):
    provider("openai", OPENAI_API_KEY="sk-test", PLANNER_MODEL="gpt-6.1-sol", PLANNER_EFFORT="high")
    assert llm.model_for("planner") == ("gpt-6.1-sol", "high")


def test_anthropic_routing(provider):
    provider("anthropic", ANTHROPIC_API_KEY="sk-ant-test", PLANNER_MODEL="", RESEARCH_MODEL="")
    assert llm.get_llm("planner").model == "claude-sonnet-5-5"
    assert llm.model_for("research") == ("claude-haiku-4-5", None)
    assert llm.system_message("x").content[0]["cache_control"] == {"type": "ephemeral"}
