from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .base import AgentIO, LLMTradingAgent


@dataclass
class StrategyAgentResult:
    name: str
    io: AgentIO


class _StrategyExpert:
    def __init__(self, name: str, system_prompt: str, llm_cfg: Dict[str, Any]) -> None:
        self.name = name
        self.agent = LLMTradingAgent(
            name=name,
            system_prompt=system_prompt,
            llm_cfg=llm_cfg,
            output_format_hint=(
                "Respond as JSON with `summary` (string) and `details` containing "
                "`signals` (array of {symbol, side, confidence, rationale, stops, sizing}) "
                "and any supporting analytics."
            ),
        )

    def run(self, context: Dict[str, Any]) -> StrategyAgentResult:
        io = self.agent.invoke(context)
        details = io.details or {}
        signals = details.get("signals") or []
        for signal in signals:
            signal.setdefault("agent", self.name)
        details["signals"] = signals
        return StrategyAgentResult(name=self.name, io=AgentIO(io.summary, details))


def _build_experts(cfg: Dict[str, Any]) -> List[_StrategyExpert]:
    llm_cfg = (cfg.get("llm") or {}).copy()
    strat_cfg = (cfg.get("strategy_agents") or {}).copy()
    prompts = strat_cfg.get("prompts") or {}
    return [
        _StrategyExpert(
            name="technical-indicator-agent",
            system_prompt=prompts.get(
                "technical",
                "Use technical indicators (moving averages, RSI, MACD, ATR) to propose trades.",
            ),
            llm_cfg=llm_cfg,
        ),
        _StrategyExpert(
            name="chart-pattern-agent",
            system_prompt=prompts.get(
                "chart_patterns",
                "Evaluate classical chart patterns (triangles, breakouts, flags) for opportunities.",
            ),
            llm_cfg=llm_cfg,
        ),
        _StrategyExpert(
            name="candlestick-agent",
            system_prompt=prompts.get(
                "candlestick",
                "Analyse candlestick structures and multi-timeframe confluence.",
            ),
            llm_cfg=llm_cfg,
        ),
        _StrategyExpert(
            name="price-action-agent",
            system_prompt=prompts.get(
                "price_action",
                "Reason about orderflow, key levels, and liquidity to propose trades.",
            ),
            llm_cfg=llm_cfg,
        ),
        _StrategyExpert(
            name="news-sentiment-agent",
            system_prompt=prompts.get(
                "news",
                "Blend latest market news with price context to find sentiment-driven trades.",
            ),
            llm_cfg=llm_cfg,
        ),
    ]


class StrategyOrchestratorAgent:
    """
    Coordinates specialised research agents and aggregates their signals.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.experts = _build_experts(cfg)

    def run(self, context: Dict[str, Any]) -> AgentIO:
        aggregated_signals: List[Dict[str, Any]] = []
        expert_reports: Dict[str, Any] = {}
        for expert in self.experts:
            result = expert.run(context)
            expert_reports[expert.name] = {
                "summary": result.io.summary,
                "details": result.io.details,
            }
            aggregated_signals.extend(result.io.details.get("signals", []))
        orchestrator_brief = {
            "experts": expert_reports,
            "signals": aggregated_signals,
            "meta": {"agent_count": len(self.experts)},
        }
        summary = (
            f"Collected {len(aggregated_signals)} candidate signals "
            f"from {len(self.experts)} experts."
        )
        return AgentIO(summary=summary, details=orchestrator_brief)
