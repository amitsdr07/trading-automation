# cli.py
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
from typing import Any, Dict

from .nodes import (
    initial_state,
    load_config,
    collect_news,
    collect_market_context,
    run_research_agents,
    evaluate_signals,
    execute_orders,
    send_report,
)
from .logging_config import configure_logging


def _last_agent_message(state: Dict[str, Any]):
    msgs = state.get("agent_messages") or []
    return msgs[-1] if msgs else None


def _dump_jsonl(agent_messages, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for m in agent_messages or []:
            f.write(json.dumps(
                {
                    "agent": getattr(m, "agent", None) if hasattr(m, "agent") else (m.get("agent") if isinstance(m, dict) else None),
                    "role": getattr(m, "role", None) if hasattr(m, "role") else (m.get("role") if isinstance(m, dict) else None),
                    "content": getattr(m, "content", None) if hasattr(m, "content") else (m.get("content") if isinstance(m, dict) else None),
                    "metadata": getattr(m, "metadata", None) if hasattr(m, "metadata") else (m.get("metadata") if isinstance(m, dict) else None),
                },
                ensure_ascii=False,
                default=str,
            ) + "\n")


def run_pipeline(log, verbose: bool = False) -> Dict[str, Any]:
    state = initial_state()

    steps = [
        ("config-loader",          "Load Config",          load_config),
        ("market-news-agent",      "Collect News",         collect_news),
        ("market-context-agent",   "Collect Market Ctx",   collect_market_context),
        ("strategy-orchestrator",  "Run Strategy Agents",  run_research_agents),
        ("signal-evaluator-agent", "Evaluate Signals",     evaluate_signals),
        ("trade-execution-agent",  "Execute Orders",       execute_orders),
        ("reporting-agent",        "Send Report",          send_report),
    ]

    for step_key, step_name, fn in steps:
        log.info("▶ %s", step_name, extra={"agent_step": step_key})
        t0 = time.perf_counter()
        try:
            state = fn(state)
        except Exception as e:
            log.exception("✗ %s failed: %s", step_name, e, extra={"agent_step": step_key})
            raise
        dt = time.perf_counter() - t0

        # Read the last agent message; your _record_agent_message already appended one.
        msg = _last_agent_message(state)
        if msg:
            # Pull attributes safely whether it's a dataclass or dict
            agent = getattr(msg, "agent", None) if hasattr(msg, "agent") else (msg.get("agent") if isinstance(msg, dict) else None)
            content = getattr(msg, "content", None) if hasattr(msg, "content") else (msg.get("content") if isinstance(msg, dict) else None)
            metadata = getattr(msg, "metadata", None) if hasattr(msg, "metadata") else (msg.get("metadata") if isinstance(msg, dict) else None)

            # Log summary line
            log.info("✓ %s [%.2fs]: %s",
                     step_name, dt, (content or "").strip(),
                     extra={"agent_step": step_key, "agent": agent})

            # Optional: log metadata as a structured JSON string when verbose
            if verbose and metadata:
                log.info("└─ metadata: %s",
                         json.dumps(metadata, ensure_ascii=False, default=str)[:4000],
                         extra={"agent_step": step_key, "agent": agent})
        else:
            log.info("✓ %s [%.2fs]: (no agent message)", step_name, dt, extra={"agent_step": step_key})

    return state


def main():
    ap = argparse.ArgumentParser(description="Agentic ATS – CLI with logging")
    ap.add_argument("--verbose", action="store_true", help="Log agent metadata")
    ap.add_argument("--jsonl", type=Path, help="Write all agent messages to JSONL")
    ap.add_argument("--save-report", type=Path, help="Save final markdown report")
    ap.add_argument("--log-file", type=Path, help="Path to log file (optional)")
    ap.add_argument("--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
    args = ap.parse_args()

    log = configure_logging(level=args.log_level.upper(), log_file=str(args.log_file) if args.log_file else None)

    state = run_pipeline(log, verbose=args.verbose)

    # Artifacts
    if args.jsonl:
        _dump_jsonl(state.get("agent_messages"), args.jsonl)
        log.info("wrote agent messages JSONL → %s", args.jsonl)

    if args.save_report:
        (args.save_report).write_text(state.get("report") or "", encoding="utf-8")
        log.info("wrote report → %s", args.save_report)

    # Tiny end summary
    orders = state.get("orders") or []
    log.info("Session Summary | symbols=%d signals=%d orders=%d realized=%.2f unrealized=%.2f",
             len(state.get("symbols") or []),
             len(state.get("strategy_signals") or []),
             len(orders),
             float(state.get("realized_pnl", 0.0)),
             float(state.get("unrealized_pnl", 0.0)),
             extra={"agent_step": "summary"})


if __name__ == "__main__":
    main()
