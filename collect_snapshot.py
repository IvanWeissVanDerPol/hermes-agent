#!/usr/bin/env python3
"""Build a unified status snapshot from all hermes subsystems."""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def safe_read_json(path, default=None):
    if not Path(path).exists():
        return default
    try:
        return json.loads(Path(path).read_text())
    except:
        return default


def get_langfuse_status():
    """Check if Langfuse is responsive."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:3200/api/public/health", timeout=3) as r:
            return {"url": "http://127.0.0.1:3200", "ok": True, "version": json.loads(r.read()).get("version")}
    except:
        return {"url": "http://127.0.0.1:3200", "ok": False}


def get_hostinger_status():
    """Check Hostinger MCP config."""
    cfg = safe_read_json("/root/.hermes/config.yaml", default={})
    # Just report config presence (avoid querying Hostinger API each time)
    config = Path("/root/.hermes/config.yaml").read_text() if Path("/root/.hermes/config.yaml").exists() else ""
    has_hostinger = "hostinger:" in config
    has_token = Path("/root/.hermes/.env").exists() and "HOSTINGER_API_TOKEN=" in Path("/root/.hermes/.env").read_text() if Path("/root/.hermes/.env").exists() else False
    return {"configured": has_hostinger and has_token}


def get_paragu_ai_status():
    """Check ParaguAI production services."""
    sites = [
        "hidrobaby-spa", "xxgym", "nde-barba", "portas-barber", "scott-tatuajes",
        "shine-nails", "arnos-barber-shop", "cronos-academy", "estudio-medieval",
        "avanibelleza", "barbershop-peluqueria", "barbye-nails", "clau-bellino",
        "lele-ferreira", "leticia-carballo", "nutrifit-spa", "peluqueria-barbershop",
        "viviesteticpy", "woman-cosmeticos"
    ]
    import urllib.request, ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    up = 0
    for s in sites:
        try:
            req = urllib.request.Request(f"https://{s}.paragu-ai.com/")
            with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
                if r.status == 200:
                    up += 1
        except:
            pass
    return {"total": len(sites), "up": up}


def main():
    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cron": safe_read_json("/root/.hermes/cron/dashboard.json", default={}),
        "observability": safe_read_json("/root/.hermes/observability/dashboard.json", default={}),
        "langfuse": get_langfuse_status(),
        "hostinger": get_hostinger_status(),
        "paragu_ai": get_paragu_ai_status(),
    }
    Path("/root/.hermes/dashboard.json").write_text(json.dumps(snapshot, indent=2))
    return snapshot


if __name__ == "__main__":
    data = main()
    print(json.dumps(data, indent=2)[:2000])
