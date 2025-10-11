from __future__ import annotations
from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from .db import DB
from .utils import load_app_config
import os

app = FastAPI(title="LangGraph Trader API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _db():
    return DB(load_app_config())

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/orders")
def orders(limit: int = 500, _: bool = Depends(require_api_key)):
    return JSONResponse(_db().fetch_orders(limit))

@app.get("/equity")
def equity(limit: int = 1000, _: bool = Depends(require_api_key)):
    return JSONResponse(_db().fetch_equity(limit))

@app.get("/positions")
def positions(_: bool = Depends(require_api_key)):
    return JSONResponse(_db().fetch_positions_latest())

@app.get("/logs")
def logs(limit: int = 500, _: bool = Depends(require_api_key)):
    return JSONResponse(_db().fetch_logs(limit))

@app.get("/report")
def report_md():
    path = "day_report.md"
    if not os.path.exists(path):
        return PlainTextResponse("Report not found", status_code=404)
    return FileResponse(path, media_type="text/markdown", filename="day_report.md")

@app.get("/equity_chart")
def equity_chart():
    path = "equity_curve.png"
    if not os.path.exists(path):
        return PlainTextResponse("Chart not found", status_code=404)
    return FileResponse(path, media_type="image/png", filename="equity_curve.png")


templates = Jinja2Templates(directory=str(__import__('pathlib').Path(__file__).parent / 'web' / 'templates'))

app.mount('/static', StaticFiles(directory=str(__import__('pathlib').Path(__file__).parent / 'web' / 'static')), name='static')

basic = HTTPBasic()

def _cfg_auth():
    return (load_app_config().get("auth") or {})

def require_api_key(request: Request):
    cfg = _cfg_auth()
    expected = cfg.get("api_key")
    if not expected:
        return True  # no API key set -> open
    key = request.headers.get("X-API-Key") or request.query_params.get("key")
    if key == expected:
        return True
    raise HTTPException(status_code=403, detail="Invalid API key")

def require_basic(credentials: HTTPBasicCredentials = Depends(basic)):
    cfg = _cfg_auth().get("basic") or {}
    user = cfg.get("username"); pwd = cfg.get("password")
    if not user:
        return True  # not configured -> open
    if credentials.username == user and credentials.password == pwd:
        return True
    raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, _: bool = Depends(require_basic)):
    return templates.TemplateResponse("dashboard.html", {"request": request})
