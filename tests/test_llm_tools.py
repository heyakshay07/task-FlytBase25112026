"""The LangChain tools are plain wrappers over the index; test them without any API key."""
import pytest

pytest.importorskip("langchain_core")

from drone_analyst.llm_agent import build_tools  # noqa: E402


def test_tools_return_grounded_data(full_run):
    a, _ = full_run
    tools = {t.name: t for t in build_tools(a)}
    assert set(tools) == {"search_frames", "semantic_search", "list_alerts", "vehicle_visits",
                          "list_entities", "daily_summary"}
    assert "07:45" in tools["search_frames"].invoke({"object": "truck"})
    assert "CRITICAL" in tools["list_alerts"].invoke({"min_severity": "CRITICAL"})
    assert "visit 3" in tools["vehicle_visits"].invoke({"object": "truck"})
    assert "ladder" in tools["list_entities"].invoke({})


def test_llm_agent_requires_key(full_run, monkeypatch):
    from drone_analyst.llm_agent import build_llm_agent
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        build_llm_agent(full_run[0])
