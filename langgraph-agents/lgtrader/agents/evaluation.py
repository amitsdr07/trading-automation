from __future__ import annotations

from typing import Any, Dict, List

from .base import AgentIO, LLMTradingAgent
from ..state import OrderInstruction, StrategySignal


class RiskManager:
    """
    Converts evaluated signals into executable order instructions respecting risk limits.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        risk_cfg = (cfg.get("risk") or {}).copy()
        self.capital = float(cfg.get("capital") or risk_cfg.get("capital", 0.0) or 0.0)
        self.max_positions = int(risk_cfg.get("max_concurrent_positions", 5))
        self.risk_per_trade_pct = float(risk_cfg.get("risk_per_trade_pct", 0.01))
        self.stop_buffer_pct = float(risk_cfg.get("stop_buffer_pct", 0.015))
        self.take_profit_multiple = float(risk_cfg.get("take_profit_multiple", 2.0))
        self.min_qty = int(risk_cfg.get("min_qty", 1))

    def _infer_price(self, signal: StrategySignal, price_map: Dict[str, float]) -> float:
        symbol = signal.get("symbol")
        if symbol and symbol in price_map:
            return float(price_map[symbol])
        ref = (
            signal.get("sizing", {}).get("reference_price")
            or signal.get("stops", {}).get("entry")
        )
        return float(ref or 0.0)

    def _calc_stop(self, side: str, entry: float) -> float:
        if entry <= 0:
            return 0.0
        buffer = self.stop_buffer_pct
        if side.upper() == "BUY":
            return entry * (1 - buffer)
        return entry * (1 + buffer)

    def _calc_target(self, side: str, entry: float, stop: float) -> float:
        if entry <= 0 or stop <= 0:
            return 0.0
        risk_per_share = abs(entry - stop)
        if risk_per_share == 0:
            return 0.0
        move = risk_per_share * self.take_profit_multiple
        if side.upper() == "BUY":
            return entry + move
        return entry - move

    def _calc_qty(self, entry: float, stop: float) -> int:
        if entry <= 0 or stop <= 0 or entry == stop:
            return 0
        risk_currency = self.capital * self.risk_per_trade_pct
        per_share = abs(entry - stop)
        qty = int(max(risk_currency / per_share, self.min_qty))
        return qty

    def plan_orders(
        self, signals: List[StrategySignal], price_map: Dict[str, float]
    ) -> List[OrderInstruction]:
        orders: List[OrderInstruction] = []
        for signal in signals:
            if len(orders) >= self.max_positions:
                break
            entry = self._infer_price(signal, price_map)
            if entry <= 0:
                continue
            stop = float(signal.get("stops", {}).get("stop_loss") or self._calc_stop(signal.get("side", "BUY"), entry))
            target = float(signal.get("stops", {}).get("take_profit") or self._calc_target(signal.get("side", "BUY"), entry, stop))
            qty = int(signal.get("sizing", {}).get("qty") or self._calc_qty(entry, stop))
            if qty <= 0:
                continue
            order: OrderInstruction = {
                "symbol": signal.get("symbol", ""),
                "side": signal.get("side", "BUY").upper(),
                "order_type": signal.get("sizing", {}).get("order_type", "MARKET"),
                "qty": qty,
                "limit_price": signal.get("sizing", {}).get("limit_price") or None,
                "stop_loss": stop or None,
                "take_profit": target or None,
                "time_in_force": signal.get("sizing", {}).get("time_in_force", "DAY"),
                "metadata": {
                    "source_agent": signal.get("agent"),
                    "confidence": signal.get("confidence"),
                    "rationale": signal.get("rationale"),
                    "risk_per_trade_pct": self.risk_per_trade_pct,
                },
            }
            orders.append(order)
        return orders


class SignalEvaluatorAgent:
    """
    Evaluates signals from research agents and partners with RiskManager to approve trades.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        llm_cfg = (cfg.get("llm") or {}).copy()
        evaluator_cfg = (cfg.get("evaluator") or {}).copy()
        system_prompt = evaluator_cfg.get(
            "system_prompt",
            "You are the head trader. Review proposed signals, stress test them "
            "against risk, and recommend orders that align with book exposure targets.",
        )
        self.agent = LLMTradingAgent(
            name="signal-evaluator-agent",
            system_prompt=system_prompt,
            llm_cfg=llm_cfg,
            output_format_hint=(
                "Return JSON with `summary`, `details.signals` (enriched signals "
                "after vetting), and `details.exclusions` (list of rejected trades)."
            ),
        )
        self.risk = RiskManager(cfg)

    def run(self, context: Dict[str, Any]) -> AgentIO:
        result = self.agent.invoke(context)
        vetted_signals: List[StrategySignal] = result.details.get("signals", [])
        if not vetted_signals:
            vetted_signals = context.get("candidate_signals", [])
        price_map = context.get("price_map", {})
        orders = self.risk.plan_orders(vetted_signals, price_map)
        details = result.details or {}
        details["orders"] = orders
        details.setdefault("vetted_signals", vetted_signals)
        return AgentIO(summary=result.summary, details=details)
