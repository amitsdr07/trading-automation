import os
import csv
from kiteconnect import KiteConnect
from dotenv import load_dotenv

# Load API key and access token
load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
with open(".kite_access_token") as f:
    ACCESS_TOKEN = f.read().strip()

# Initialize Kite API
kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

# Choose exchange: NSE / BSE / NFO / CDS / MCX etc.
exchange = "NFO"

print(f"Fetching instrument list for {exchange}...")

# Fetch all instruments for the chosen exchange
instruments = kite.instruments(exchange)

# File to save data
output_file = f"{exchange}_instruments.csv"

# Write to CSV file
with open(output_file, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "instrument_token",
            "exchange_token",
            "tradingsymbol",
            "name",
            "last_price",
            "expiry",
            "strike",
            "tick_size",
            "lot_size",
            "instrument_type",
            "segment",
            "exchange",
        ],
    )
    writer.writeheader()
    writer.writerows(instruments)

print(f"✅ Saved {len(instruments)} instruments to {output_file}")
