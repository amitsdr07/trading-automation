from __future__ import annotations

from typing import Any, Dict, List

from .base import AgentIO, LLMTradingAgent
from ..brokers.base import make_broker
from ..state import OrderInstruction


class TradeExecutionAgent:
    """
    Bridges evaluated orders to the configured broker (Angel, Zerodha, or paper).
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        llm_cfg = (cfg.get("llm") or {}).copy()
        execution_cfg = (cfg.get("execution") or {}).copy()
        system_prompt = execution_cfg.get(
            "system_prompt",
            "You are a trading operations specialist. Confirm the readiness of each order, "
            "highlight broker-specific nuances, and summarise execution feedback.",
        )
        self.agent = LLMTradingAgent(
            name="trade-execution-agent",
            system_prompt=system_prompt,
            llm_cfg=llm_cfg,
            output_format_hint=(
                "Return JSON with `summary` and `details` containing "
                "`acknowledged_orders` and `pre_trade_checks`."
            ),
        )
        self.cfg = cfg

    def _dispatch_orders(self, orders: List[OrderInstruction]) -> List[Dict[str, Any]]:
        broker = make_broker(self.cfg)
        executions: List[Dict[str, Any]] = []
        for order in orders:
            payload = {
                "symbol": order["symbol"],
                "side": order["side"],
                "qty": int(order["qty"]),
                "price": order.get("limit_price") or 0.0,
                "meta": order.get("metadata") or {},
                "type": order.get("order_type", "MARKET"),
                "time_in_force": order.get("time_in_force", "DAY"),
                "stop_loss": order.get("stop_loss"),
                "take_profit": order.get("take_profit"),
            }
            if order.get("order_type", "MARKET").upper() == "MARKET":
                resp = broker.place_market(payload)
            else:
                # Brokers will fallback to market implementation by default
                resp = broker.place_market(payload)
            executions.append({"order": order, "response": resp})
        return executions

    def run(self, context: Dict[str, Any]) -> AgentIO:
        orders: List[OrderInstruction] = context.get("orders", [])
        llm_result = self.agent.invoke({"orders": orders, "session": context})
        broker_responses = self._dispatch_orders(orders)
        details = llm_result.details or {}
        details["executions"] = broker_responses
        return AgentIO(summary=llm_result.summary, details=details)
