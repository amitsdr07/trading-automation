import os
import pyotp
from SmartApi import SmartConnect
from dotenv import load_dotenv

load_dotenv()

# ---- Store these as ENV variables for safety ----
API_KEY      = os.getenv("ANGEL_API_KEY")
CLIENT_CODE  = os.getenv("ANGEL_CLIENT_CODE")
PASSWORD     = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET  = os.getenv("ANGEL_TOTP_SECRET")  # Base32 secret from Angel's TOTP setup

# ---- Generate TOTP on runtime ----
totp = pyotp.TOTP(TOTP_SECRET).now()
print("Generated OTP:", totp)

# ---- Create SmartConnect object ----
smart_api = SmartConnect(api_key=API_KEY)

# ---- Login with client_code, password, and TOTP ----
data = smart_api.generateSession(
    clientCode=CLIENT_CODE,
    password=PASSWORD,
    totp=totp
)

#print("Login response:", data)
jwtToken = data['data']['jwtToken']
print(jwtToken)

# ---- Use refresh token if needed ----
# refreshToken = data['data']['refreshToken']
# userProfile = smart_api.getProfile(refreshToken)
# print("User Profile:", userProfile)
