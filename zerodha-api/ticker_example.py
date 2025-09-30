# ticker_example.py (for kiteconnect==4.2.0)
import os
import time
from kiteconnect import KiteTicker, KiteConnect
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")  # optional; fallback to file
if not ACCESS_TOKEN and os.path.exists(".kite_access_token"):
    with open(".kite_access_token") as f:
        ACCESS_TOKEN = f.read().strip()

if not API_KEY or not ACCESS_TOKEN:
    raise RuntimeError("Missing KITE_API_KEY or access token. Run the auth helper first.")

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

# Map symbols -> instrument tokens (cache instruments in real apps)
nse_instruments = kite.instruments("NSE")
sym_to_token = {i["tradingsymbol"]: i["instrument_token"] for i in nse_instruments}

watchlist = ["INFY", "TCS"]  # edit your symbols here
missing = [s for s in watchlist if s not in sym_to_token]
if missing:
    raise KeyError(f"Symbols not found on NSE: {missing}")

tokens = [sym_to_token[s] for s in watchlist]

kws = KiteTicker(API_KEY, ACCESS_TOKEN)

def on_ticks(ws, ticks):
    for t in ticks:
        print("Tick:", t.get("instrument_token"), t.get("last_price"))

def on_connect(ws, response):
    print("Connected. Subscribing…")
    ws.subscribe(tokens)
    ws.set_mode(ws.MODE_FULL, tokens)

def on_close(ws, code, reason):
    print("Closed:", code, reason)

def on_error(ws, code, reason):
    print("Error:", code, reason)

def on_reconnect(ws, attempts_count):
    print("Reconnecting… attempt", attempts_count)

def on_noreconnect(ws):
    print("Reconnection failed; stopping.")

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_close = on_close
kws.on_error = on_error
kws.on_reconnect = on_reconnect
kws.on_noreconnect = on_noreconnect

# --- Reconnect options for kiteconnect==4.2.0
def start():
    try:
        # Most 4.2.0 wheels accept these:
        kws.connect(
            threaded=True,
            reconnect=True,
            reconnect_interval=5,
            reconnect_tries=50,        # some builds use this name
        )
    except TypeError:
        # Fallback: a few builds use reconnect_max_tries
        try:
            kws.connect(
                threaded=True,
                reconnect=True,
                reconnect_interval=5,
                reconnect_max_tries=50,   # alternate kw
            )
        except TypeError:
            print("[i] This build ignores reconnect kwargs; connecting without them.")
            kws.connect(threaded=True)

start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    kws.close()
