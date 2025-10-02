# search_scrip.py
import os
import http.client
import json
from dotenv import load_dotenv
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_token import get_jwt_token_from_smartapi, AuthError

load_dotenv()  # load from .env
API_HOST = "apiconnect.angelone.in"

def search_scrip(jwt_token: str, api_key: str) -> str:
    conn = http.client.HTTPSConnection(API_HOST)
    payload = json.dumps({
     "exchange": "NSE",
     "searchscrip": "SBIN"
})
    headers = {
        "Authorization": f"{jwt_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "CLIENT_LOCAL_IP",
        "X-ClientPublicIP": "CLIENT_PUBLIC_IP",
        "X-MACAddress": "MAC_ADDRESS",
        "X-PrivateKey": api_key,
    }
     
    conn.request("POST", "/rest/secure/angelbroking/order/v1/searchScrip", payload, headers)
    res = conn.getresponse()
    return res.read().decode("utf-8")

if __name__ == "__main__":
    try:
        api_key = os.getenv("ANGEL_API_KEY")
        if not api_key:
            raise ValueError("ANGEL_API_KEY not set in .env")

        jwt_token = get_jwt_token_from_smartapi()
        print(jwt_token)
        portfolio = search_scrip(jwt_token, api_key)
        print(portfolio)

    except (AuthError, Exception) as e:
        print(f"Failed: {e}")