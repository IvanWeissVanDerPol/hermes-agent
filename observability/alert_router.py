#!/usr/bin/env python3
"""
Alert Router - Multi-channel alert dispatcher (A-3).

Sends alerts to Telegram, WhatsApp, email, or logs based on severity + config.

Severity levels:
  - critical: All channels
  - warning:  Telegram + log
  - info:     log only
"""
import os
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ALERT_LOG = "/root/.hermes/observability/alerts.log"
ENV_PATH = "/root/.hermes/.env"


def _get_token(name):
    """Read token from .env."""
    if Path(ENV_PATH).exists():
        for line in Path(ENV_PATH).read_text().split("\n"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(name)


def send_telegram(chat_id, text):
    """Send via Telegram bot."""
    token = _get_token("TELEGRAM_BOT_TOKEN")
    if not token:
        return False, "no TELEGRAM_BOT_TOKEN"
    try:
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                return True, "sent"
            return False, result
    except Exception as e:
        return False, str(e)[:200]


def send_whatsapp_callmebot(phone, text):
    """Send via CallMeBot (free WhatsApp gateway)."""
    apikey = _get_token("CALLMEBOT_APIKEY")
    if not apikey:
        return False, "no CALLMEBOT_APIKEY"
    try:
        text_enc = urllib.parse.quote(text)
        url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={text_enc}&apikey={apikey}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, "sent"
    except Exception as e:
        return False, str(e)[:200]


def alert(message, level="info", channels=None, context=None):
    """Send an alert via specified channels.

    level: critical | warning | info
    channels: list of [telegram, whatsapp, log] (default: based on level)
    """
    if channels is None:
        channels = {
            "critical": ["telegram", "whatsapp", "log"],
            "warning": ["telegram", "log"],
            "info": ["log"],
        }.get(level, ["log"])

    # Always log to file
    os.makedirs(os.path.dirname(ALERT_LOG), exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "context": context or {},
        "channels_attempted": channels,
    }
    results = {}

    if "log" in channels:
        with open(ALERT_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
        results["log"] = "ok"

    if "telegram" in channels:
        chat_id = _get_token("TELEGRAM_HOME_CHANNEL") or _get_token("TELEGRAM_CHAT_ID")
        if chat_id:
            ok, detail = send_telegram(chat_id, f"[{level.upper()}] {message}")
            results["telegram"] = detail
        else:
            results["telegram"] = "no chat_id"

    if "whatsapp" in channels:
        phone = _get_token("CALLMEBOT_PHONE")
        if phone:
            ok, detail = send_whatsapp_callmebot(phone, f"[{level.upper()}] {message}")
            results["whatsapp"] = detail
        else:
            results["whatsapp"] = "no phone"

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: alert_router.py <level> <message>")
        sys.exit(1)
    level = sys.argv[1]
    message = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "test alert"
    result = alert(message, level=level)
    print(json.dumps(result, indent=2))
