"""Thin mem0 REST server (official API shape) backed by Host A Qdrant.

Env contract (mirrors the legacy mem0-server that was removed from Docker Hub):
  QDRANT_URL          required, e.g. http://38.9.96.179:6333
  QDRANT_COLLECTION   default mem0
  ANTHROPIC_API_KEY   wired to llm provider anthropic when present
  LLM_PROVIDER        default anthropic
  LLM_MODEL           default claude-sonnet-4-6
  EMBEDDER            default fastembed (local, no API key)
  EMBEDDING_MODEL     default all-MiniLM-L6-v2 (384 dims, matches qdrant mem0 collection)
"""

import os

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from mem0 import Memory


QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "mem0")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic" if ANTHROPIC_API_KEY else "openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
EMBEDDER = os.environ.get("EMBEDDER", "fastembed")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


def build_config():
    cfg = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "url": QDRANT_URL,
                "collection_name": QDRANT_COLLECTION,
                "embedding_model_dims": 384,
            },
        },
        "embedder": {"provider": EMBEDDER, "config": {"model": EMBEDDING_MODEL}},
        "history_db_path": "/app/history/history.db",
    }
    if LLM_PROVIDER == "anthropic":
        cfg["llm"] = {
            "provider": "anthropic",
            "config": {
                "api_key": ANTHROPIC_API_KEY,
                "model": LLM_MODEL,
                "temperature": 0.1,
                "max_tokens": 2000,
            },
        }
    else:
        cfg["llm"] = {
            "provider": "openai",
            "config": {"api_key": os.environ.get("OPENAI_API_KEY", ""), "model": LLM_MODEL, "temperature": 0.1},
        }
    return cfg


memory = Memory.from_config(build_config())

app = FastAPI(title="Mem0 REST APIs", version="1.0.0", redirect_slashes=False)


class Message(BaseModel):
    role: str
    content: str


class MemoryCreate(BaseModel):
    messages: list[Message] = Field(..., description="List of messages to store.")
    user_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    metadata: dict | None = None
    infer: bool | None = None


class SearchRequest(BaseModel):
    query: str
    user_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    top_k: int | None = None
    threshold: float | None = None


@app.get("/healthz")
def healthz():
    return {"status": "ok", "vector_store": f"qdrant@{QDRANT_URL}/{QDRANT_COLLECTION}", "llm": LLM_PROVIDER, "embedder": EMBEDDER}


@app.post("/memories", summary="Create memories")
def add_memory(body: MemoryCreate):
    if not any([body.user_id, body.agent_id, body.run_id]):
        raise HTTPException(status_code=400, detail="At least one identifier (user_id, agent_id, run_id) is required.")
    params = {k: v for k, v in body.model_dump().items() if v is not None and k != "messages"}
    return memory.add(messages=[m.model_dump() for m in body.messages], **params)


@app.get("/memories", summary="Get memories")
def get_memories(
    user_id: str | None = None,
    agent_id: str | None = None,
    run_id: str | None = None,
    top_k: int | None = Query(None, ge=0, le=1000),
):
    if not any([user_id, agent_id, run_id]):
        raise HTTPException(status_code=400, detail="At least one identifier (user_id, agent_id, run_id) is required.")
    filters = {k: v for k, v in {"user_id": user_id, "agent_id": agent_id, "run_id": run_id}.items() if v}
    params = {"filters": filters}
    if top_k is not None:
        params["top_k"] = top_k
    return memory.get_all(**params)


@app.post("/search", summary="Search memories")
def search_memories(req: SearchRequest):
    filters = {}
    for entity_key in ("user_id", "agent_id", "run_id"):
        val = getattr(req, entity_key)
        if val:
            filters[entity_key] = val
    params = {}
    if req.top_k is not None:
        params["top_k"] = req.top_k
    if req.threshold is not None:
        params["threshold"] = req.threshold
    return memory.search(query=req.query, filters=filters, **params)


@app.get("/", include_in_schema=False)
def home():
    return {"status": "ok", "docs": "/docs"}
