from __future__ import annotations
from typing import Dict, Any

def make_markdown(state: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"# Daily Report ({state.get('segment','')})\n")
    lines.append(f"Symbols: {', '.join(state.get('symbols', []))}")
    lines.append(f"Broker: {state.get('broker_name')}")
    lines.append(f"Trades taken: {sum(state.get('trades_by_strategy', {}).values())}")
    lines.append(f"PnL (est): {state.get('pnl', 0.0):.2f}\n")
    lines.append("## Orders")
    for o in state.get("orders", []):
        lines.append(f"- {o.get('symbol')} {o.get('side')} x{o.get('qty')} @ {o.get('price', '-')}: {o.get('status')}")
    lines.append("\n## Logs")
    for l in state.get("logs", []):
        lines.append(f"- {l}")
    return "\n".join(lines)

def _send_email(cfg: Dict[str, Any], subject: str, body: str) -> Dict[str, Any]:
    settings = (cfg.get("report") or {}).get("email") or {}
    if not settings.get("enable"): return {"email": "disabled"}
    import smtplib
    from email.mime.text import MIMEText
    host = settings.get("smtp_host",""); port = int(settings.get("smtp_port",587))
    user = settings.get("username",""); pwd = settings.get("password","")
    from_addr = settings.get("from", user); to_addrs = settings.get("to", [])
    if isinstance(to_addrs, str): to_addrs = [to_addrs]
    if not (host and user and pwd and to_addrs): return {"email": "missing_config"}
    msg = MIMEText(body, _subtype="plain", _charset="utf-8")
    msg["Subject"] = subject; msg["From"] = from_addr; msg["To"] = ", ".join(to_addrs)
    try:
        smtp = smtplib.SMTP(host, port, timeout=10)
        if settings.get("use_tls", True): smtp.starttls()
        smtp.login(user, pwd)
        smtp.sendmail(from_addr, to_addrs, msg.as_string())
        smtp.quit()
        return {"email": "sent", "to": to_addrs}
    except Exception as e:
        return {"email": f"error: {e}"}

def _send_slack(cfg: Dict[str, Any], text: str) -> Dict[str, Any]:
    settings = (cfg.get("report") or {}).get("slack") or {}
    if not settings.get("enable"): return {"slack": "disabled"}
    url = settings.get("webhook_url","")
    if not url: return {"slack": "missing_webhook"}
    import json, urllib.request
    try:
        req = urllib.request.Request(url, data=json.dumps({"text": text}).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"slack": f"ok:{resp.status}"}
    except Exception as e:
        return {"slack": f"error: {e}"}

def deliver_report(cfg: Dict[str, Any], markdown: str) -> Dict[str, Any]:
    subject = "EOD Trading Report"
    email_res = _send_email(cfg, subject, markdown)
    slack_res = _send_slack(cfg, markdown)
    return {"email": email_res, "slack": slack_res}

def make_equity_chart(state: Dict[str, Any], out_path: str = "equity_curve.png") -> str:
    try:
        import matplotlib.pyplot as plt
        xs = [i for i,_ in enumerate(state.get("equity_curve", []))]
        ys = [pt.get("equity", 0.0) for pt in state.get("equity_curve", [])]
        plt.figure()
        plt.plot(xs, ys)  # do not set colors/styles per project constraints
        plt.title("Equity Curve")
        plt.xlabel("Samples")
        plt.ylabel("Equity")
        plt.tight_layout()
        plt.savefig(out_path)
        plt.close()
        return out_path
    except Exception as e:
        return ""
