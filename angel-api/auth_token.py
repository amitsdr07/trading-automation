# auth_token.py
import os
import pyotp
from dotenv import load_dotenv
from SmartApi import SmartConnect

load_dotenv()  # load variables from .env

class AuthError(Exception):
    pass

def get_jwt_token_from_smartapi() -> str:
    """
    Logs in via Angel One SmartAPI using env vars and returns a JWT string.
    Expected env vars:
      ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PASSWORD, ANGEL_TOTP_SECRET
    """
    API_KEY     = os.getenv("ANGEL_API_KEY")
    CLIENT_CODE = os.getenv("ANGEL_CLIENT_CODE")
    PASSWORD    = os.getenv("ANGEL_PASSWORD")
    TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

    # Validate
    missing = [k for k, v in {
        "ANGEL_API_KEY": API_KEY,
        "ANGEL_CLIENT_CODE": CLIENT_CODE,
        "ANGEL_PASSWORD": PASSWORD,
        "ANGEL_TOTP_SECRET": TOTP_SECRET,
    }.items() if not v]
    if missing:
        raise AuthError(f"Missing env vars: {', '.join(missing)}")

    # Generate runtime TOTP
    totp = pyotp.TOTP(TOTP_SECRET).now()

    # Login
    smart_api = SmartConnect(api_key=API_KEY)
    resp = smart_api.generateSession(
        clientCode=CLIENT_CODE,
        password=PASSWORD,
        totp=totp
    )

    data = (resp or {}).get("data") or {}
    #print(data)
    jwt_token = data.get("jwtToken") or data.get("accessToken")

    if not jwt_token:
        raise AuthError(f"Could not obtain JWT from SmartAPI response: {resp}")

    return jwt_token
