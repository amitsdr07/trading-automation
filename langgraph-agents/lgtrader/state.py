from __future__ import annotations
from typing import Dict, Any, List, Optional, TypedDict


class AgentMessage(TypedDict, total=False):
    agent: str
    role: str
    content: str
    metadata: Dict[str, Any]


class StrategySignal(TypedDict, total=False):
    agent: str
    symbol: str
    side: str
    confidence: float
    rationale: str
    time_horizon: str
    stops: Dict[str, Any]
    sizing: Dict[str, Any]


class OrderInstruction(TypedDict, total=False):
    symbol: str
    side: str
    order_type: str
    qty: float
    limit_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    time_in_force: str
    metadata: Dict[str, Any]

class Position(TypedDict, total=False):
    symbol: str
    side: str
    qty: int
    avg_price: float
    stop_loss: float
    target: float
    strategy: str

class Order(TypedDict, total=False):
    symbol: str
    side: str
    qty: int
    price: float
    status: str
    broker_id: Optional[str]
    meta: Dict[str, Any]

class TraderState(TypedDict, total=False):
    cfg: Dict[str, Any]
    segment: str
    symbols: List[str]
    enabled_strategies: List[str]
    strategy_budgets: Dict[str, Dict[str, Any]]
    broker_name: str
    tokens_map: Dict[str, Any]

    seed_done: bool
    entries_enabled: bool
    stop_new_entries: bool
    positions: Dict[str, Position]
    trades_by_strategy: Dict[str, int]
    pnl: float
    max_daily_loss: float
    max_trades_per_day: int
    trailing_stop_pct: float
    trailing_trigger_pct: float
    segment_capital_cap: float
    global_capital: float

    history: Dict[str, List[Dict[str, Any]]]
    buffers: Dict[str, List[float]]
    last_price: Dict[str, float]

    logs: List[Dict[str, Any]]
    agent_messages: List[AgentMessage]
    orders: List[Order]
    report: str
    # finance
    cash: float
    equity: float
    equity_curve: list
    peak_equity: float
    max_drawdown: float
    realized_pnl: float
    unrealized_pnl: float
    # idempotency
    order_index: Dict[str, int]
    pending_orders: List[Dict[str, Any]]
    news_brief: Dict[str, Any]
    market_context: Dict[str, Any]
    research_insights: Dict[str, Any]
    strategy_signals: List[StrategySignal]
    evaluated_orders: List[OrderInstruction]
    execution_results: List[Dict[str, Any]]
    report_payload: Dict[str, Any]
