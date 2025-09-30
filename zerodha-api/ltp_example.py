import os
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
with open(".kite_access_token") as f:
    ACCESS_TOKEN = f.read().strip()

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

symbols = ["NSE:INFY", "NSE:TCS", "NSE:RELIANCE", "NSE:HDFCBANK"]
ltp_all = kite.ltp(symbols)

for s, v in ltp_all.items():
    print(s, v["last_price"])
