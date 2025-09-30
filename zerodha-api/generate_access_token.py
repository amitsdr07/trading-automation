import os
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()  # loads from .env

API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
REQUEST_TOKEN = os.getenv("KITE_REQUEST_TOKEN")

kite = KiteConnect(api_key=API_KEY)

data = kite.generate_session(REQUEST_TOKEN, api_secret=API_SECRET)
access_token = data["access_token"]
print("ACCESS_TOKEN =", access_token)

# Save to file for reuse
with open(".kite_access_token", "w") as f:
    f.write(access_token)
