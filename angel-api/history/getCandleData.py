# get_candledata.py
import os
import http.client
from dotenv import load_dotenv
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_token import get_jwt_token_from_smartapi, AuthError

load_dotenv()  # load from .env
API_HOST = "apiconnect.angelone.in"

def get_candledata(jwt_token: str, api_key: str) -> str:
    conn = http.client.HTTPSConnection(API_HOST)
    payload = json.dumps({
     "exchange": "NSE",
     "symboltoken": "3045",
     "interval": "FIVE_MINUTE",
     "fromdate": "2025-04-02 09:30",
     "todate": "2025-04-02 11:00"
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
    conn.request("POST", "/rest/secure/angelbroking/historical/v1/getCandleData", payload, headers)
    res = conn.getresponse()
    return res.read().decode("utf-8")

if __name__ == "__main__":
    try:
        api_key = os.getenv("ANGEL_API_KEY")
        if not api_key:
            raise ValueError("ANGEL_API_KEY not set in .env")

        jwt_token = get_jwt_token_from_smartapi()
        print(jwt_token)
        portfolio = get_candledata(jwt_token, api_key)
        print(portfolio)

    except (AuthError, Exception) as e:
        print(f"Failed: {e}")
