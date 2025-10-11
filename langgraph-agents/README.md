# LangGraph Multi-Agent Trading Orchestrator

Hands-off workflow that mirrors the Indian cash market window (09:15–15:15 IST).  
A cooperative set of LangGraph-powered LLM agents monitor the tape, propose ideas, control risk, execute trades, and dispatch reports.

## Agent Stack

1. **Config Loader** – hydrates runtime state and guardrails from `config.yaml`.  
2. **Market News Agent** – ingests configured feeds and extracts actionable sentiment.  
3. **Market Context Agent** – builds a quantitative backdrop (historical stats, GIFT Nifty, breadth).  
4. **Strategy Orchestrator** – spins up five specialists in parallel: technical indicators, chart patterns, candlesticks, price action, and news sentiment.  
5. **Signal Evaluator & Risk Manager** – validates suggestions, applies capital limits, and sizes trades.  
6. **Trade Execution Agent** – performs pre-trade checks and routes orders to Angel / Zerodha (or the paper broker).  
7. **Reporting Agent** – compiles the session recap and sends it once the market closes.

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
python -m lgtrader.cli --demo
```

`--demo` runs the entire LangGraph immediately. Live mode waits until 09:15 IST, executes the trading phase, blocks until 15:15 IST, and then publishes the report.

## Scheduling

- Opening leg (load → execute) triggers at **09:15 IST** by default.  
- Reporting waits until **15:15 IST**.  
- Override these times via `trading_window.start_time_ist` / `end_time_ist`.

## Configuration Highlights

| Section | Purpose |
| ------- | ------- |
| `llm` | Model/provider for every agent (supports `openai` and `azure-openai`). |
| `news` | Input feeds for the Market News Agent. Provide REST endpoints returning JSON. |
| `market_data` | Watchlist (Yahoo Finance tickers), pre-market index, lookback length. |
| `strategy_agents.prompts` | Tailor prompts for each specialist agent. |
| `risk` | Desk-level guardrails consumed by the evaluator (max positions, risk per trade, buffers). |
| `broker` / `instruments` | Credentials and token maps for Angel or Zerodha adapters (defaults to paper). |
| `reporting` / `report` | Prompt and delivery settings (email / Slack) for the EOD summary. |

Review the updated `config.yaml` for a fully annotated example.

## Broker Integration

- Default broker is `paper`, which logs orders without touching external APIs.  
- Flip `broker.broker` to `angel` or `zerodha` when credentials are ready.  
- Actual routing lives in `lgtrader/brokers/angel.py` and `lgtrader/brokers/zerodha.py`; extend those to support more order types or authentication flows.

## Reporting

The reporting agent writes Markdown to `day_report.md` and hands it to `report.deliver_report`, which can email and/or post to Slack. Tune tone, attribution depth, or next steps by editing `reporting.system_prompt`.

## Extending the System

- Add more specialists by extending `StrategyOrchestratorAgent` or wiring new prompt entries.  
- Plug additional data vendors inside `agents/data.py`.  
- Strengthen real-world controls inside `agents/evaluation.py` (risk) and `agents/execution.py` (OMS integration).

## Safety Notes

- Leave the system in paper mode until you have validated prompts and controls end-to-end.  
- LLM outputs are probabilistic—hard risk caps in `config.yaml` remain the final defence.  
- Always dry-run changes (`python -m lgtrader.cli --demo`) before the next trading session.
