#!/usr/bin/env python3
"""
End-to-end helper for Zerodha Kite authentication flow. (run this each new trading day)

What it does:
1) Builds the login URL
2) Opens your browser
3) Captures request_token automatically if redirecting to http://127.0.0.1:<port>/callback,
   otherwise prompts you to paste request_token
   example : https://techskillmentor.com/?action=login&type=login&status=success&request_token=B5v7KNTe1e3GMvzDZ4EKJFVso1nfBbsK
4) Exchanges request_token for access_token
5) Saves access_token to .kite_access_token
6) Optionally writes KITE_ACCESS_TOKEN to .env for convenience

Usage:
    python setup_kite_auth.py
    # or override defaults:
    python setup_kite_auth.py --port 8765 --write-env

Prereqs:
    - Fill KITE_API_KEY and KITE_API_SECRET in .env
    - (Optional) Set KITE_REDIRECT_URL to http://127.0.0.1:8765/callback (or another localhost port)
      and configure the SAME redirect URL in Zerodha developer console.
"""

import os
import sys
import argparse
import threading
import webbrowser
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
REDIRECT_URL = os.getenv("KITE_REDIRECT_URL", "https://techskillmentor.com/")  # optional

LOGIN_URL = f"https://kite.zerodha.com/connect/login?v=3&api_key={API_KEY}" if API_KEY else None
ACCESS_TOKEN_PATH = ".kite_access_token"
ENV_PATH = ".env"

def die(msg: str, code: int = 1):
    print(f"[!] {msg}")
    sys.exit(code)

def check_prereqs():
    if not API_KEY:
        die("KITE_API_KEY missing in .env")
    if not API_SECRET:
        die("KITE_API_SECRET missing in .env")

class TokenHandler(BaseHTTPRequestHandler):
    # Simple handler to catch ?request_token=... on /callback
    request_token_value = None
    done_event = None

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query or "")
        rt = qs.get("request_token", [None])[0]

        if rt:
            TokenHandler.request_token_value = rt
            # Respond nicely to the browser
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Request token received. You can close this tab and return to the terminal.</h2>")
            if TokenHandler.done_event:
                TokenHandler.done_event.set()
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h3>No request_token found in the URL.</h3>")

    # Silence default console logs
    def log_message(self, format, *args):
        return

def start_local_server(host: str, port: int, done_event: threading.Event):
    TokenHandler.done_event = done_event
    httpd = HTTPServer((host, port), TokenHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

def write_access_token_files(access_token: str, write_env: bool):
    # Write to .kite_access_token
    with open(ACCESS_TOKEN_PATH, "w") as f:
        f.write(access_token)
    print(f"[+] Saved access_token to {ACCESS_TOKEN_PATH}")

    if write_env:
        # Update or add KITE_ACCESS_TOKEN in .env (idempotent)
        lines = []
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, "r") as f:
                lines = f.read().splitlines()

        found = False
        for i, line in enumerate(lines):
            if line.startswith("KITE_ACCESS_TOKEN="):
                lines[i] = f"KITE_ACCESS_TOKEN={access_token}"
                found = True
                break
        if not found:
            lines.append(f"KITE_ACCESS_TOKEN={access_token}")

        with open(ENV_PATH, "w") as f:
            f.write("\n".join(lines) + ("\n" if lines and not lines[-1].endswith("\n") else ""))
        print(f"[+] Updated KITE_ACCESS_TOKEN in {ENV_PATH}")

def exchange_request_token(request_token: str) -> str:
    kite = KiteConnect(api_key=API_KEY)
    data = kite.generate_session(request_token, api_secret=API_SECRET)
    return data["access_token"]

def main():
    check_prereqs()

    parser = argparse.ArgumentParser(description="Kite auth helper")
    parser.add_argument("--port", type=int, default=8765, help="Local server port for redirect capture")
    parser.add_argument("--host", default="127.0.0.1", help="Local server host")
    parser.add_argument("--write-env", action="store_true", help="Also write KITE_ACCESS_TOKEN to .env")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open the browser")
    args = parser.parse_args()

    if not LOGIN_URL:
        die("Unable to build login URL – is KITE_API_KEY set?")

    print("\n--- Zerodha Kite Authentication ---\n")
    print("[1] Opening login URL. Sign in and complete OTP.\n")

    print(f"Login URL:\n{LOGIN_URL}\n")
    if not args.no_browser:
        try:
            webbrowser.open(LOGIN_URL, new=1, autoraise=True)
        except Exception as e:
            print(f"[!] Could not open browser automatically: {e}")

    # Decide capture mode
    capture_mode = "manual"
    target_host, target_port, target_path = None, None, None
    if REDIRECT_URL:
        parsed_ru = urlparse(REDIRECT_URL)
        if parsed_ru.scheme in ("http", "https") and parsed_ru.hostname in ("127.0.0.1", "localhost"):
            target_host = parsed_ru.hostname
            target_port = parsed_ru.port or args.port
            target_path = parsed_ru.path or "/callback"
            if target_path == "/callback" and target_host == "127.0.0.1":
                capture_mode = "auto"
            else:
                # We’ll still try as long as host is localhost
                capture_mode = "auto"

    request_token = None

    if capture_mode == "auto":
        print("[2] Waiting to capture request_token from redirect...")
        print(f"    Ensure your app Redirect URL is set to: {REDIRECT_URL}")
        print(f"    Starting local server at http://{args.host}:{args.port}{target_path}\n")

        done_event = threading.Event()
        server_thread = threading.Thread(
            target=start_local_server,
            args=(args.host, args.port, done_event),
            daemon=True
        )
        server_thread.start()

        # Wait until we get request_token or user interrupts
        try:
            done_event.wait(timeout=300)  # 5 minutes
        except KeyboardInterrupt:
            print("\n[!] Interrupted by user.")
            sys.exit(1)

        request_token = TokenHandler.request_token_value
        if not request_token:
            print("[!] Did not capture request_token within timeout. Falling back to manual mode.\n")
            capture_mode = "manual"

    if capture_mode == "manual":
        print("[2] Manual mode selected.")
        print("    After you finish logging in, you’ll be redirected to your configured Redirect URL.")
        print("    Copy the 'request_token' query parameter value from that URL and paste it below.\n")
        try:
            request_token = input("Enter request_token: ").strip()
        except KeyboardInterrupt:
            print("\n[!] Interrupted by user.")
            sys.exit(1)

    if not request_token:
        die("No request_token provided or captured.")

    print("\n[3] Exchanging request_token for access_token...")
    try:
        access_token = exchange_request_token(request_token)
    except Exception as e:
        die(f"Failed to exchange request_token: {e}")

    print("[4] Success! access_token acquired.")
    write_access_token_files(access_token, write_env=args.write_env)

    print("\n[5] You can now run your scripts (ltp_example.py, historical_example.py, ticker_example.py).")
    print(f"    They will read the token from {ACCESS_TOKEN_PATH}.\n")
    print("[6] Note: access_token expires daily. Re-run this script next trading day.\n")

if __name__ == "__main__":
    main()
