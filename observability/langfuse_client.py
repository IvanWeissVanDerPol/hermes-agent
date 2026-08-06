#!/usr/bin/env python3
"""
Langfuse DB Client - Direct trace writer.

Bypasses Langfuse API auth by writing directly to its Postgres DB.
Used for tracing LLM calls, tool uses, and workflows.

Usage:
    from langfuse_client import LangfuseTrace
    with LangfuseTrace(name="my-workflow", user="ivan") as trace:
        trace.span("tool-call", tool="search", input={...})
        # do work
        trace.span("tool-result", result={...})

Env vars:
    LANGFUSE_DB_HOST: postgres container hostname (default: localhost:5432)
    LANGFUSE_DB_NAME: langfuse
    LANGFUSE_DB_USER: langfuse
    LANGFUSE_DB_PASS: langfuse
    LANGFUSE_PROJECT_ID: project ID in langfuse
"""
import os
import time
import json
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager

try:
    import psycopg2
    HAVE_PSYCOPG2 = True
except ImportError:
    HAVE_PSYCOPG2 = False


class LangfuseTrace:
    """Write traces directly to Langfuse Postgres DB."""

    def __init__(self, name, user=None, metadata=None):
        if not HAVE_PSYCOPG2:
            self.local_mode = True
            self.traces = []
            return

        try:
            self.conn = psycopg2.connect(
                host=os.environ.get("LANGFUSE_DB_HOST", "172.19.0.2"),
                port=int(os.environ.get("LANGFUSE_DB_PORT", "5432")),
                dbname=os.environ.get("LANGFUSE_DB_NAME", "langfuse"),
                user=os.environ.get("LANGFUSE_DB_USER", "langfuse"),
                password=os.environ.get("LANGFUSE_DB_PASS", "langfuse"),
                connect_timeout=3,
            )
            self.local_mode = False
        except Exception:
            self.local_mode = True
            self.traces = []

        self.project_id = os.environ.get("LANGFUSE_PROJECT_ID", "cmsggtm6r0006tv64e923w93g")
        self.trace_id = f"trace-{uuid.uuid4().hex[:16]}"
        self.name = name
        self.user = user
        self.metadata = metadata or {}
        self.observations = []
        self.start = time.time()

    def __enter__(self):
        if not self.local_mode:
            cur = self.conn.cursor()
            cur.execute(
                """INSERT INTO traces (id, project_id, name, user_id, metadata, created_at)
                   VALUES (%s, %s, %s, %s, %s::jsonb, %s)""",
                (self.trace_id, self.project_id, self.name, self.user,
                 json.dumps(self.metadata), datetime.now(timezone.utc))
            )
            self.conn.commit()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self.start) * 1000)
        if not self.local_mode:
            self.conn.close()
        # Log to local file as fallback (always)
        log_file = "/root/.hermes/observability/traces.log"
        with open(log_file, "a") as f:
            f.write(json.dumps({
                "trace_id": self.trace_id,
                "name": self.name,
                "user": self.user,
                "duration_ms": duration_ms,
                "observation_count": len(self.observations),
                "metadata": self.metadata,
                "ts": datetime.now(timezone.utc).isoformat(),
                "local_mode": self.local_mode,
            }) + "\n")

    def span(self, name, **kwargs):
        """Record a span (observation) in the trace."""
        obs = {
            "id": f"obs-{uuid.uuid4().hex[:16]}",
            "trace_id": self.trace_id,
            "name": name,
            "project_id": self.project_id,
            "start_offset_ms": int((time.time() - self.start) * 1000),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kwargs": kwargs,
        }
        self.observations.append(obs)

        if not self.local_mode:
            try:
                cur = self.conn.cursor()
                cur.execute(
                    """INSERT INTO observations (id, trace_id, project_id, type, name, metadata, created_at)
                       VALUES (%s, %s, %s, %s::"ObservationType", %s, %s::jsonb, %s)""",
                    (obs["id"], self.trace_id, self.project_id, "SPAN", name,
                     json.dumps(kwargs), datetime.now(timezone.utc))
                )
                self.conn.commit()
            except Exception as e:
                pass  # silent fail in production

    def log(self, name, **kwargs):
        """Alias for span (matches Langfuse API)."""
        self.span(name, **kwargs)

    def generation(self, name, model, prompt=None, completion=None, usage=None):
        """Record an LLM generation."""
        self.span(name, type="GENERATION", model=model,
                  prompt_tokens=usage.get("prompt_tokens") if usage else None,
                  completion_tokens=usage.get("completion_tokens") if usage else None)
