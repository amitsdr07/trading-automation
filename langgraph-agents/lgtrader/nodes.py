from __future__ import annotations

from typing import Any, Dict, List

from .agents.data import MarketDataAgent, MarketNewsAgent
from .agents.evaluation import SignalEvaluatorAgent
from .agents.execution import TradeExecutionAgent
from .agents.reporting import ReportingAgent
from .agents.strategy import StrategyOrchestratorAgent
from .state import AgentMessage, OrderInstruction, StrategySignal, TraderState
from .utils import load_app_config, now_ist


def initial_state() -> TraderState:
    return {
        "cfg": {},
        "segment": "EQ",
        "symbols": [],
        "enabled_strategies": [],
        "strategy_budgets": {},
        "broker_name": "paper",
        "tokens_map": {},
        "seed_done": False,
        "entries_enabled": False,
        "stop_new_entries": False,
        "positions": {},
        "trades_by_strategy": {},
        "pnl": 0.0,
        "max_daily_loss": 0.0,
        "max_trades_per_day": 0,
        "trailing_stop_pct": 0.0,
        "trailing_trigger_pct": 0.0,
        "segment_capital_cap": 0.0,
        "global_capital": 0.0,
        "history": {},
        "buffers": {},
        "last_price": {},
        "logs": [],
        "agent_messages": [],
        "orders": [],
        "report": "",
        "cash": 0.0,
        "equity": 0.0,
        "equity_curve": [],
        "peak_equity": 0.0,
        "max_drawdown": 0.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "order_index": {},
        "pending_orders": [],
        "news_brief": {},
        "market_context": {},
        "research_insights": {},
        "strategy_signals": [],
        "evaluated_orders": [],
        "execution_results": [],
        "report_payload": {},
    }


def _record_agent_message(
    state: TraderState, agent: str, summary: str, metadata: Dict[str, Any]
) -> None:
    state["agent_messages"].append(
        AgentMessage(
            agent=agent,
            role="assistant",
            content=summary,
            metadata=metadata,
        )
    )
    state["logs"].append({agent: summary})


def load_config(state: TraderState) -> TraderState:
    cfg = load_app_config()
    segment = (cfg.get("segment") or "EQ").upper()
    segment_cfg = (cfg.get("segments") or {}).get(segment, {})
    symbols = segment_cfg.get("watchlist") or cfg.get("watchlist") or []
    risk_cfg = cfg.get("risk") or {}
    broker_cfg = cfg.get("broker") or {}
    state.update(
        {
            "cfg": cfg,
            "segment": segment,
            "symbols": symbols,
            "enabled_strategies": segment_cfg.get("enabled_strategies") or [],
            "strategy_budgets": cfg.get("strategy_budgets") or {},
            "broker_name": (broker_cfg.get("broker") or "paper").lower(),
            "tokens_map": (cfg.get("instruments") or {}).get(
                broker_cfg.get("broker", "paper"), {}
            ),
            "max_daily_loss": float(
                segment_cfg.get("max_daily_loss") or risk_cfg.get("max_daily_loss", 0.0)
            ),
            "max_trades_per_day": int(
                segment_cfg.get("max_trades_per_day")
                or risk_cfg.get("max_trades_per_day", 0)
            ),
            "trailing_stop_pct": float(risk_cfg.get("trailing_stop_pct", 0.0)),
            "trailing_trigger_pct": float(risk_cfg.get("trailing_trigger_pct", 0.0)),
            "segment_capital_cap": float(segment_cfg.get("capital_cap") or 0.0),
            "global_capital": float(cfg.get("capital") or 0.0),
        }
    )
    state["entries_enabled"] = True
    _record_agent_message(
        state,
        "config-loader",
        f"Loaded configuration for {segment}; tracking {len(symbols)} symbols.",
        {"segment": segment, "symbols": symbols},
    )
    return state


def collect_news(state: TraderState) -> TraderState:
    agent = MarketNewsAgent(state["cfg"])
    result = agent.run({"symbols": state["symbols"], "timestamp": now_ist().isoformat()})
    state["news_brief"] = {"summary": result.summary, **result.details}
    _record_agent_message(
        state,
        "market-news-agent",
        result.summary,
        state["news_brief"],
    )
    return state


def collect_market_context(state: TraderState) -> TraderState:
    agent = MarketDataAgent(state["cfg"])
    result = agent.run(
        {
            "symbols": state["symbols"],
            "segment": state["segment"],
            "news": state.get("news_brief"),
        }
    )
    state["market_context"] = {"summary": result.summary, **result.details}
    # update last price map from raw data if possible
    raw_history = (
        state["market_context"]
        .get("raw_market_data", {})
        .get("history", {})
    )
    price_map: Dict[str, float] = {}
    for symbol, series in raw_history.items():
        if not series:
            continue
        maybe_last = next(
            (entry for entry in reversed(series) if "close" in entry), None
        )
        if maybe_last:
            price_map[symbol] = float(maybe_last.get("close", 0.0))
    state["last_price"] = price_map
    _record_agent_message(
        state,
        "market-context-agent",
        result.summary,
        state["market_context"],
    )
    return state


def _build_strategy_context(state: TraderState) -> Dict[str, Any]:
    return {
        "segment": state.get("segment"),
        "symbols": state.get("symbols"),
        "news": state.get("news_brief"),
        "market_context": state.get("market_context"),
        "prices": state.get("last_price"),
    }


def _normalise_signal(raw: Dict[str, Any]) -> StrategySignal:
    signal: StrategySignal = {
        "agent": str(raw.get("agent") or "unknown"),
        "symbol": str(raw.get("symbol") or ""),
        "side": str(raw.get("side") or "BUY").upper(),
        "confidence": float(raw.get("confidence") or 0.5),
        "rationale": str(raw.get("rationale") or ""),
        "time_horizon": str(raw.get("time_horizon") or "intraday"),
        "stops": dict(raw.get("stops") or {}),
        "sizing": dict(raw.get("sizing") or {}),
    }
    return signal


def _normalise_order(raw: Dict[str, Any]) -> OrderInstruction:
    order: OrderInstruction = {
        "symbol": str(raw.get("symbol") or ""),
        "side": str(raw.get("side") or "BUY").upper(),
        "order_type": str(raw.get("order_type") or "MARKET").upper(),
        "qty": float(raw.get("qty") or 0),
        "limit_price": raw.get("limit_price"),
        "stop_loss": raw.get("stop_loss"),
        "take_profit": raw.get("take_profit"),
        "time_in_force": str(raw.get("time_in_force") or "DAY"),
        "metadata": dict(raw.get("metadata") or {}),
    }
    return order


def run_research_agents(state: TraderState) -> TraderState:
    agent = StrategyOrchestratorAgent(state["cfg"])
    context = _build_strategy_context(state)
    result = agent.run(context)
    state["research_insights"] = {"summary": result.summary, **result.details}
    signals = result.details.get("signals", [])
    state["strategy_signals"] = [
        _normalise_signal(sig) for sig in signals if sig.get("symbol")
    ]
    _record_agent_message(
        state,
        "strategy-orchestrator",
        result.summary,
        state["research_insights"],
    )
    return state


def evaluate_signals(state: TraderState) -> TraderState:
    agent = SignalEvaluatorAgent(state["cfg"])
    context = {
        "candidate_signals": [dict(sig) for sig in state.get("strategy_signals", [])],
        "news": state.get("news_brief"),
        "market_context": state.get("market_context"),
        "price_map": state.get("last_price"),
    }
    result = agent.run(context)
    state["evaluated_orders"] = [
        _normalise_order(order) for order in result.details.get("orders", [])
    ]
    state["research_insights"]["vetted_signals"] = result.details.get(
        "vetted_signals", []
    )
    _record_agent_message(
        state,
        "signal-evaluator-agent",
        result.summary,
        {"orders": [dict(o) for o in state["evaluated_orders"]]},
    )
    return state


def execute_orders(state: TraderState) -> TraderState:
    if not state.get("evaluated_orders"):
        _record_agent_message(
            state,
            "trade-execution-agent",
            "No executable orders for the current session.",
            {},
        )
        return state
    agent = TradeExecutionAgent(state["cfg"])
    context = {
        "orders": [dict(order) for order in state["evaluated_orders"]],
        "price_map": state.get("last_price"),
    }
    result = agent.run(context)
    state["execution_results"] = result.details.get("executions", [])
    state["orders"] = [exec_res.get("order") for exec_res in state["execution_results"]]
    _record_agent_message(
        state,
        "trade-execution-agent",
        result.summary,
        {"executions": state["execution_results"]},
    )
    return state


def send_report(state: TraderState) -> TraderState:
    agent = ReportingAgent(state["cfg"])
    context = {
        "news": state.get("news_brief"),
        "market_context": state.get("market_context"),
        "signals": state.get("strategy_signals"),
        "orders": state.get("orders"),
        "executions": state.get("execution_results"),
        "pnl": state.get("pnl"),
    }
    result = agent.run(context)
    state["report_payload"] = {"summary": result.summary, **result.details}
    state["report"] = state["report_payload"].get("markdown", "")
    _record_agent_message(
        state,
        "reporting-agent",
        result.summary,
        state["report_payload"],
    )
    return state
