#!/usr/bin/env python3
"""
LLM Tracer - Auto-trace LLM calls with model, tokens, latency.
Works with OpenAI-compatible APIs.

Usage:
    from llm_tracer import traced_llm_call
    result = traced_llm_call(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "hello"}],
        user="ivan",
        workflow="draft-email",
    )
"""
import os
import time
import json
from datetime import datetime, timezone

# Use local trace store as fallback
TRACES_FILE = "/root/.hermes/observability/llm_traces.log"
STATS_FILE = "/root/.hermes/observability/llm_stats.json"


def traced_llm_call(model, messages, user=None, workflow=None, **kwargs):
    """Wrap an LLM call and trace it."""
    import sys
    # Lazy imports
    try:
        import openai
        client = openai.OpenAI(
            api_key=kwargs.pop("api_key", os.environ.get("OPENAI_API_KEY", "sk-test")),
            base_url=kwargs.pop("base_url", os.environ.get("OPENAI_BASE_URL"))
        )
    except ImportError:
        client = None

    trace = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "user": user,
        "workflow": workflow,
        "messages_count": len(messages),
        "kwargs": {k: v for k, v in kwargs.items() if k not in ("api_key",)},
    }

    start = time.time()
    try:
        if client:
            response = client.chat.completions.create(model=model, messages=messages, **kwargs)
            result_text = response.choices[0].message.content
            usage = response.usage
            trace.update({
                "status": "ok",
                "latency_ms": int((time.time() - start) * 1000),
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
                "result_chars": len(result_text) if result_text else 0,
            })
            _log(trace)
            return result_text
        else:
            # Stub for testing
            result_text = f"[stub response for {model}]"
            trace.update({"status": "stub", "result_chars": len(result_text)})
            _log(trace)
            return result_text
    except Exception as e:
        trace.update({"status": "error", "error": str(e)[:200],
                      "latency_ms": int((time.time() - start) * 1000)})
        _log(trace)
        raise


def _log(trace):
    """Append trace to file + update stats."""
    os.makedirs(os.path.dirname(TRACES_FILE), exist_ok=True)
    with open(TRACES_FILE, "a") as f:
        f.write(json.dumps(trace) + "\n")
    _update_stats(trace)


def _update_stats(trace):
    """Update aggregate stats per model."""
    stats = {}
    if os.path.exists(STATS_FILE):
        try:
            stats = json.loads(open(STATS_FILE).read())
        except:
            stats = {}
    model = trace["model"]
    if model not in stats:
        stats[model] = {"calls": 0, "tokens": 0, "errors": 0, "total_latency_ms": 0}
    s = stats[model]
    s["calls"] += 1
    s["tokens"] += trace.get("total_tokens", 0)
    if trace["status"] == "error":
        s["errors"] += 1
    s["total_latency_ms"] += trace.get("latency_ms", 0)
    open(STATS_FILE, "w").write(json.dumps(stats, indent=2))


if __name__ == "__main__":
    # Test the tracer in stub mode
    import os
    if os.environ.get("OPENAI_API_KEY", "sk-test") == "sk-test":
        # No real key - stub mode
        from llm_tracer import _log
        _log({"ts": "2026-08-05T19:00:00Z", "model": "stub", "user": "ivan",
              "workflow": "smoke-test", "messages_count": 1, "kwargs": {},
              "status": "stub", "latency_ms": 0, "prompt_tokens": 0,
              "completion_tokens": 0, "total_tokens": 0, "result_chars": 50})
        print("Stub trace logged")
    else:
        result = traced_llm_call(
            model="test-model",
            messages=[{"role": "user", "content": "hello"}],
            user="ivan",
            workflow="smoke-test",
        )
        print(f"Result: {result}")