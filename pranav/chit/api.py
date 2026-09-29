"""Chit HTTP API.

Run from the repo root:
    uvicorn pranav.chit.api:app --host 127.0.0.1 --port 8000

Environment variables:
    CHIT_CHECKPOINT  path to checkpoint   (default: checkpoints/latest.pt)
    CHIT_API_KEY     if set, every request except /health must send
                     the header  X-API-Key: <value>
"""
import os
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .bridge import Bridge, Context
from .runtime import ChitRuntime

CHECKPOINT = os.environ.get("CHIT_CHECKPOINT", "checkpoints/latest.pt")
API_KEY = os.environ.get("CHIT_API_KEY")

_state = {"runtime": None, "bridge": None, "error": None}
_lock = threading.Lock()  # one generation at a time; the model is not built for parallel calls


@asynccontextmanager
async def lifespan(app: FastAPI):
    if Path(CHECKPOINT).exists():
        try:
            rt = ChitRuntime.from_checkpoint(CHECKPOINT)
            _state.update(runtime=rt, bridge=Bridge(rt), error=None)
        except Exception as e:  # bad/incompatible checkpoint: stay up, report via /health
            _state["error"] = f"{type(e).__name__}: {e}"
    else:
        _state["error"] = f"checkpoint not found: {CHECKPOINT} (train first)"
    yield


app = FastAPI(title="Chit API", version="0.1.0", lifespan=lifespan)


def require_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and not (x_api_key and secrets.compare_digest(x_api_key, API_KEY)):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def get_runtime() -> ChitRuntime:
    if _state["runtime"] is None:
        raise HTTPException(status_code=503, detail=_state["error"] or "model not loaded")
    return _state["runtime"]


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    tokens: int = Field(default=100, ge=1, le=500)
    temperature: float = Field(default=0.7, ge=0.1, le=2.0)
    top_k: int = Field(default=50, ge=1, le=256)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    task: str = Field(default="chat", max_length=50)


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    memory_type: str = "experience"
    importance: float = Field(default=0.5, ge=0, le=1)
    tags: list[str] = []


@app.get("/health")
def health():
    return {"status": "ok" if _state["runtime"] else "no_model",
            "model_loaded": _state["runtime"] is not None,
            "error": _state["error"]}


@app.post("/generate", dependencies=[Depends(require_key)])
def generate(r: GenerateRequest):
    rt = get_runtime()
    with _lock:
        text = rt.generate(r.prompt, r.tokens, r.temperature, r.top_k)
    return {"text": text}


@app.post("/chat", dependencies=[Depends(require_key)])
def chat(r: ChatRequest):
    get_runtime()
    with _lock:
        d = _state["bridge"].process(Context(user_input=r.message, task=r.task))
    return {"text": d.text, "metadata": d.metadata}


@app.post("/memory", dependencies=[Depends(require_key)])
def add_memory(m: MemoryIn):
    with _lock:
        return get_runtime().remember(m.content, m.memory_type, m.importance, m.tags)


@app.get("/memory/search", dependencies=[Depends(require_key)])
def search_memory(q: str = Query(min_length=1, max_length=200), limit: int = Query(5, ge=1, le=50)):
    with _lock:
        return {"results": get_runtime().recall(q, limit)}
