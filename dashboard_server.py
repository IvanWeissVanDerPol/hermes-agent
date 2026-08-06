#!/usr/bin/env python3
"""
Hermes Dashboard Server - HTTP server with API key auth.
Reads /root/.hermes/dashboard.json + serves HTML + JSON.

Usage:
    dashboard_server.py [--port 3201] [--host 127.0.0.1]
"""
import os
import sys
import json
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

DASHBOARD_JSON = "/root/.hermes/dashboard.json"
DASHBOARD_HTML = "/root/.hermes/dashboard.html"
AUTH_TOKEN = None  # set from KIKI_API_KEY env var or arg


class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Public health endpoint
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/":
            self._serve_html()
            return
        if self.path == "/api/dashboard":
            self._serve_json()
            return
        if self.path == "/api/cron":
            self._serve_cron_json()
            return
        if self.path == "/api/langfuse":
            self._serve_langfuse()
            return
        self._json(404, {"error": "not found"})

    def _check_auth(self):
        """Check Authorization header."""
        if not AUTH_TOKEN:
            return True  # disabled
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {AUTH_TOKEN}"

    def _serve_html(self):
        try:
            with open(DASHBOARD_HTML) as f:
                html = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _serve_json(self):
        if not self._check_auth():
            self._json(401, {"error": "unauthorized"})
            return
        try:
            with open(DASHBOARD_JSON) as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data.encode())
        except FileNotFoundError:
            self._json(404, {"error": "dashboard.json not found"})

    def _serve_cron_json(self):
        if not self._check_auth():
            self._json(401, {"error": "unauthorized"})
            return
        try:
            with open("/root/.hermes/cron/dashboard.json") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data.encode())
        except FileNotFoundError:
            self._json(404, {"error": "cron dashboard not found"})

    def _serve_langfuse(self):
        """Proxy to local Langfuse."""
        if not self._check_auth():
            self._json(401, {"error": "unauthorized"})
            return
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:3200/api/public/health", timeout=3) as r:
                data = r.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self._json(503, {"error": str(e)})

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        # Silent logging
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=3201)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--auth-token", default=os.environ.get("DASHBOARD_TOKEN"))
    args = parser.parse_args()

    global AUTH_TOKEN
    AUTH_TOKEN = args.auth_token

    server = HTTPServer((args.host, args.port), AuthHandler)
    print(f"Dashboard server: http://{args.host}:{args.port}/")
    if AUTH_TOKEN:
        print(f"  Auth: Bearer {AUTH_TOKEN[:8]}...")
    else:
        print(f"  Auth: DISABLED (no token)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
