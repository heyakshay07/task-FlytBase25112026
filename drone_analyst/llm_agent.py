"""Optional LLM layer: a LangGraph ReAct agent whose tools are the frame index.

The deterministic `SecurityAnalystAgent.ask()` already answers the common questions offline.
This layer adds free-form reasoning ("is there a pattern in tonight's visits?") by letting an
LLM (Groq by default) call the same index through tools, with the bounded context snapshot
from `ContextManager.prompt_context()` injected into the system prompt.

Requires: pip install langchain-core langgraph langchain-groq   and   GROQ_API_KEY
"""
from __future__ import annotations

import os

from langchain_core.tools import tool

from .agent import SecurityAnalystAgent
from .models import Severity

SYSTEM = """You are the Drone Security Analyst for a fixed property. Answer ONLY from tool results
and the context below; if the data does not contain the answer, say so. Cite timestamps (HH:MM)
and locations. Be concise and flag anything that needs human follow-up.

CONTEXT SNAPSHOT
{context}"""


def build_tools(agent: SecurityAnalystAgent) -> list:
    idx = agent.index

    @tool
    def search_frames(object: str = "", location: str = "", start_hhmm: str = "", end_hhmm: str = "") -> str:
        """Find indexed frames by object (truck, person, 'blue ford f150'...), location and/or
        time-of-day window (HH:MM, wrap-around allowed e.g. 22:00-05:00)."""
        rows = idx.frames(obj=object or None, location=location or None,
                          tod_start=start_hhmm or None, tod_end=end_hhmm or None, limit=40)
        return "\n".join(f"{r['hhmm']} @{r['location']}: {r['description']}" for r in rows) or "no frames"

    @tool
    def semantic_search(query: str) -> str:
        """Free-text similarity search over frame descriptions."""
        return "\n".join(f"{r['hhmm']} @{r['location']}: {r['description']}"
                         for r in idx.semantic_search(query, 5)) or "no matches"

    @tool
    def list_alerts(min_severity: str = "INFO") -> str:
        """List generated alerts at or above a severity (INFO, LOW, MEDIUM, HIGH, CRITICAL)."""
        return "\n".join(str(a) for a in idx.alerts(Severity.parse(min_severity))) or "no alerts"

    @tool
    def vehicle_visits(object: str = "") -> str:
        """Entry/exit times for vehicles matching a term (e.g. 'truck'); empty = all vehicles."""
        return "\n".join(f"{v['label']}: visit {v['visit_no']} {v['start_ts'][11:16]}-"
                         f"{(v['end_ts'] or 'still on site')[-8:-3] if v['end_ts'] else 'still on site'}"
                         for v in idx.visits(object or None)) or "no visits"

    @tool
    def list_entities() -> str:
        """Every distinct object seen, with first/last seen and number of frames."""
        return agent.ask("what objects were in the video").text

    @tool
    def daily_summary() -> str:
        """Deterministic summary of the monitored period."""
        return agent.summary()

    return [search_frames, semantic_search, list_alerts, vehicle_visits, list_entities, daily_summary]


def build_llm_agent(agent: SecurityAnalystAgent, model: str = "llama-3.3-70b-versatile"):
    from langchain_groq import ChatGroq
    from langgraph.prebuilt import create_react_agent

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("Set GROQ_API_KEY to use the LLM agent (the offline agent needs no key).")
    llm = ChatGroq(model=model, temperature=0)
    return create_react_agent(llm, build_tools(agent),
                              prompt=SYSTEM.format(context=agent.ctx.prompt_context()))


def ask_llm(agent: SecurityAnalystAgent, question: str, **kw) -> str:
    graph = build_llm_agent(agent, **kw)
    out = graph.invoke({"messages": [("user", question)]})
    return out["messages"][-1].content
