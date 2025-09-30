import os, datetime as dt
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
with open(".kite_access_token") as f:
    ACCESS_TOKEN = f.read().strip()

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

instruments = kite.instruments("NSE")
infy = next(i for i in instruments if i["tradingsymbol"] == "INFY" and i["segment"] == "NSE")
token = infy["instrument_token"]

to_dt = dt.datetime.now()
from_dt = to_dt - dt.timedelta(days=5)

candles = kite.historical_data(
    instrument_token=token,
    from_date=from_dt,
    to_date=to_dt,
    interval="5minute",
    continuous=False,
    oi=True
)

for c in candles[:5]:
    print(c)
