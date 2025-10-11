from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

from .base import AgentIO, LLMTradingAgent
from ..report import deliver_report


class ReportingAgent:
    """
    Crafts a final run summary and dispatches it through configured channels.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        llm_cfg = (cfg.get("llm") or {}).copy()
        reporting_cfg = (cfg.get("reporting") or {}).copy()
        self.cfg = cfg
        system_prompt = reporting_cfg.get(
            "system_prompt",
            "You are the portfolio manager wrapping up the trading session. "
            "Summarise the day with focus on PnL attribution, risk usage, "
            "and actionable follow-ups.",
        )
        self.agent = LLMTradingAgent(
            name="reporting-agent",
            system_prompt=system_prompt,
            llm_cfg=llm_cfg,
            output_format_hint=(
                "Return JSON with `summary` and `details` containing `sections` array. "
                "Each section should be {title, body}. Include a `next_steps` list."
            ),
        )

    def _build_payload(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "generated_at": dt.datetime.utcnow().isoformat(),
            "news": context.get("news"),
            "market_context": context.get("market_context"),
            "signals": context.get("signals"),
            "orders": context.get("orders"),
            "executions": context.get("executions"),
            "pnl": context.get("pnl"),
        }

    def _render_markdown(self, sections: List[Dict[str, Any]], summary: str) -> str:
        lines = [f"# Daily Trading Report", "", f"**Summary:** {summary}", ""]
        for sec in sections:
            title = sec.get("title", "Untitled")
            body = sec.get("body", "")
            lines.append(f"## {title}")
            lines.append(body)
            lines.append("")
        return "\n".join(lines)

    def run(self, context: Dict[str, Any]) -> AgentIO:
        payload = self._build_payload(context)
        result = self.agent.invoke(payload)
        sections: List[Dict[str, Any]] = result.details.get("sections", [])
        markdown = self._render_markdown(sections, result.summary)
        delivery_result = deliver_report(self.cfg, markdown)
        details = result.details or {}
        details["markdown"] = markdown
        details["delivery"] = delivery_result
        return AgentIO(summary=result.summary, details=details)
