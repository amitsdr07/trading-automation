# get_brokerage.py
import os
import requests
import http.client
from dotenv import load_dotenv
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_token import get_jwt_token_from_smartapi, AuthError

load_dotenv()  # load from .env

# API Endpoint
API_URL = "https://apiconnect.angelone.in/rest/secure/angelbroking/brokerage/v1/estimateCharges"

def get_brokerage(jwt_token: str, client_code: str) -> str:
    # Headers with generated JWT token and client code
    headers = {
       "Content-Type": "application/json",
       "Accept": "application/json",
       "Authorization": f"{jwt_token}",
       "X-User-Type": "USER",
       "X-Client-Code": client_code,  # Pass client code dynamically
       "X-Source-ID": "WEB"
    }

    # Request Payload
    data = {
        "orders": [
        {
            "product_type": "DELIVERY",
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "800",
            "exchange": "NSE",
            "symbol_name": "745AS33",
            "token": "17117"
        },
        {
            "product_type": "DELIVERY",
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "800",
            "exchange": "BSE",
            "symbol_name": "PIICL151223",
            "token": "726131"
        }
    ]
    }

    # Make the API Request
    response = requests.post(API_URL, headers=headers, data=json.dumps(data))
    # Print Response
    print("Status Code:", response.status_code)
    print("Response JSON:", response.json())
    return response.json()


if __name__ == "__main__":
    try:
        client_code = os.getenv("ANGEL_CLIENT_CODE")
        if not client_code:
            raise ValueError("ANGEL_CLIENT_CODE not set in .env")

        jwt_token = get_jwt_token_from_smartapi()
        print(jwt_token)
        portfolio = get_brokerage(jwt_token, client_code)
        print(portfolio)

    except (AuthError, Exception) as e:
        print(f"Failed: {e}")
================================
import requests
import json
import http.client

# API Endpoint
url = "https://apiconnect.angelone.in/rest/secure/angelbroking/brokerage/v1/estimateCharges"

# Load JSON file 
with open("../credentials.json", "r") as file:
    data = json.load(file)

# Extract credentials
client_code = data.get("client_code", "")
password = data.get("password", "")
totp = data.get("totp", "")
api_key = data.get("api_key", "")

def get_jwt_token(client_code, password, totp, api_key):
    conn = http.client.HTTPSConnection("apiconnect.angelone.in")
    payload = json.dumps({
        "clientcode": client_code,
        "password": password,
        "totp": totp,
        "state": "STATE_VARIABLE"
    })
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-UserType': 'USER',
        'X-SourceID': 'WEB',
        'X-ClientLocalIP': 'CLIENT_LOCAL_IP',
        'X-ClientPublicIP': 'CLIENT_PUBLIC_IP',
        'X-MACAddress': 'MAC_ADDRESS',
        'X-PrivateKey': api_key
    }
    conn.request("POST", "/rest/auth/angelbroking/user/v1/loginByPassword", payload, headers)
    res = conn.getresponse()
    data = res.read()
    response_json = json.loads(data.decode("utf-8"))
    return response_json.get("data", {}).get("jwtToken")
    return response_json.get("data", {}).get("jwtToken")

# Get JWT Token
token = get_jwt_token(client_code, password, totp, api_key)

# Headers with generated JWT token and client code
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {token}",
    "X-User-Type": "USER",
    "X-Client-Code": client_code,  # Pass client code dynamically
    "X-Source-ID": "WEB"
}

# Request Payload
data = {
    "orders": [
        {
            "product_type": "DELIVERY",
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "800",
            "exchange": "NSE",
            "symbol_name": "745AS33",
            "token": "17117"
        },
        {
            "product_type": "DELIVERY",
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "800",
            "exchange": "BSE",
            "symbol_name": "PIICL151223",
            "token": "726131"
        }
    ]
}

# Make the API Request
response = requests.post(url, headers=headers, data=json.dumps(data))

# Print Response
print("Status Code:", response.status_code)
print("Response JSON:", response.json())
