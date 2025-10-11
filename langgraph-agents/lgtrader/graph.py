from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import TraderState
from .nodes import (
    collect_market_context,
    collect_news,
    execute_orders,
    evaluate_signals,
    initial_state,
    load_config,
    run_research_agents,
    send_report,
)

def build_graph():
    g = StateGraph(TraderState)
    g.add_node("load_config", load_config)
    g.add_node("collect_news", collect_news)
    g.add_node("collect_market_context", collect_market_context)
    g.add_node("run_research_agents", run_research_agents)
    g.add_node("evaluate_signals", evaluate_signals)
    g.add_node("execute_orders", execute_orders)
    g.add_node("send_report", send_report)

    g.set_entry_point("load_config")
    g.add_edge("load_config", "collect_news")
    g.add_edge("collect_news", "collect_market_context")
    g.add_edge("collect_market_context", "run_research_agents")
    g.add_edge("run_research_agents", "evaluate_signals")
    g.add_edge("evaluate_signals", "execute_orders")
    g.add_edge("execute_orders", "send_report")
    g.add_edge("send_report", END)

    return g.compile()
