from __future__ import annotations
import argparse, time
from datetime import timedelta
from .utils import now_ist, load_app_config
from .graph import build_graph
from .nodes import initial_state

def run_all(graph, state):
    # Traverse the linear graph step-by-step
    for step in ["load_config","seed_history","open_live","tick_loop","stop_new_entries","flatten_positions","summarize_day","send_report"]:
        state = graph.invoke(state, {"config": {"__node__": step}})
    return state

def main():
    p = argparse.ArgumentParser("LangGraph Day Runner")
    p.add_argument("--demo", action="store_true", help="Run fast demo (sim ticks) without wall-clock waits")
    args = p.parse_args()

    app = load_app_config()
    start = app.get("trading_window", {}).get("start_time_ist", "09:30")
    end = app.get("trading_window", {}).get("end_time_ist", "15:30")

    graph = build_graph()
    state = initial_state()

    if args.demo:
        state = run_all(graph, state)
        print(state.get("report",""))
        return

    # Real-time: block between phases
    # 1) load_config & seed immediately
    for step in ["load_config","seed_history"]:
        state = graph.invoke(state, {"config": {"__node__": step}})

    # 2) wait until market open
    h, m = map(int, start.split(":"))
    t_open = now_ist().replace(hour=h, minute=m, second=0, microsecond=0)
    if now_ist() < t_open:
        time.sleep((t_open - now_ist()).total_seconds())
    state = graph.invoke(state, {"config": {"__node__": "open_live"}})

    # 3) tick_loop (in this skeleton it runs a bounded loop; replace with real WS loop for production)
    state = graph.invoke(state, {"config": {"__node__": "tick_loop"}})

    # 4) stop_new_entries at close-10min
    h_end, m_end = map(int, end.split(":"))
    t_close = now_ist().replace(hour=h_end, minute=m_end, second=0, microsecond=0)
    t_stop = t_close - timedelta(minutes=10)
    if now_ist() < t_stop:
        time.sleep((t_stop - now_ist()).total_seconds())
    state = graph.invoke(state, {"config": {"__node__": "stop_new_entries"}})

    # 5) flatten ~1s before close
    t_exit = t_close - timedelta(seconds=1)
    if now_ist() < t_exit:
        time.sleep((t_exit - now_ist()).total_seconds())
    state = graph.invoke(state, {"config": {"__node__": "flatten_positions"}})

    # 6) summarize and send report at close
    if now_ist() < t_close:
        time.sleep((t_close - now_ist()).total_seconds())
    for step in ["summarize_day","send_report"]:
        state = graph.invoke(state, {"config": {"__node__": step}})

    print(state.get("report",""))

if __name__ == "__main__":
    main()
