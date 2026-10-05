"""Chit HTTP API.

Run from the repo root:
    uvicorn pranav.chit.api:app --host 127.0.0.1 --port 8000

Environment variables:
    CHIT_CHECKPOINT  path to checkpoint   (default: checkpoints/latest.pt)
    CHIT_API_KEY     if set, every request except /health must send
                     the header  X-API-Key: <value>
    CHIT_MEMORY_PATH memory file          (default: data/memory.json)

    Training and knowledge API (see docs/TRAINING_API.md, docs/KNOWLEDGE_API.md):
    CHIT_CONFIG_DIR       directory of training configs     (default: configs)
    CHIT_JOBS_DIR         per-job training output           (default: checkpoints/jobs)
    CHIT_MAX_TRAIN_STEPS  upper bound for training.max_steps (default: 100000)
    CHIT_KNOWLEDGE_DB     knowledge database                (default: data/knowledge.db)
    CHIT_MAX_DATASET_MB   upper bound for a generated training set (default: 200)
    Training data (see docs/DATA_API.md):
    CHIT_DATA_DIR         folder POST /data/split reads corpus files from (default: data)
    Chat sessions (see docs/SESSIONS.md):
    CHIT_SESSIONS_DB      session database                  (default: data/sessions.db)
    CHIT_SESSION_TTL_DAYS delete sessions idle this long at start-up (default: 30; 0 = keep forever)
    CHIT_MAX_SESSION_TURNS  messages kept per session       (default: 200)
    CHIT_HISTORY_TURNS    most recent messages sent to the model as context (default: 8)
    CHIT_ALLOW_UNAUTHENTICATED_TRAINING
                          "1" enables training/knowledge without CHIT_API_KEY (local dev only)

Run with a single worker (the default). Model state and the training job
registry live in this process, so --workers N would give each worker its own
model and allow N concurrent training runs.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
import secrets
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, Union

import torch
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__, datasets
from .bridge import Bridge, Context
from .config import ChitConfig, ConfigError, DataSourceConfig, ModelConfig, load_config
from .embeddings import SentenceTransformerProvider
from .jobs import JobConflict, JobFinished, JobNotFound, TrainingJobManager
from .knowledge import KnowledgeError, KnowledgeStore, build_dataset
from .inference import InferenceManager, InferenceOverloaded
from .memory import SQLiteMemoryStore
from .promotion_state import recover_promotion
from .runtime import ChitRuntime
from .sessions import SessionNotFound, SessionStore
from .summarization import SessionSummaryWorker
from .tokenizer import ByteTokenizer, create_tokenizer
from .training import ARCHITECTURE_KEYS

log = logging.getLogger(__name__)

CHECKPOINT = os.environ.get("CHIT_CHECKPOINT", "checkpoints/latest.pt")
API_KEY = os.environ.get("CHIT_API_KEY")
CONFIG_DIR = os.environ.get("CHIT_CONFIG_DIR", "configs")
JOBS_DIR = os.environ.get("CHIT_JOBS_DIR", "checkpoints/jobs")
MAX_TRAIN_STEPS = int(os.environ.get("CHIT_MAX_TRAIN_STEPS", "100000"))
MEMORY_PATH = os.environ.get("CHIT_MEMORY_PATH", "data/memory.json")
MEMORY_DB = os.environ.get("CHIT_MEMORY_DB")
EMBEDDING_MODEL_PATH = os.environ.get("CHIT_EMBEDDING_MODEL_PATH")
EMBEDDING_MODEL_VERSION = os.environ.get("CHIT_EMBEDDING_MODEL_VERSION")
EMBEDDING_SEMANTIC_THRESHOLD = os.environ.get("CHIT_EMBEDDING_SEMANTIC_THRESHOLD")
KNOWLEDGE_DB = os.environ.get("CHIT_KNOWLEDGE_DB", "data/knowledge.db")
MAX_DATASET_BYTES = int(float(os.environ.get("CHIT_MAX_DATASET_MB", "200")) * 1024 * 1024)
ALLOW_UNAUTHENTICATED_TRAINING = os.environ.get("CHIT_ALLOW_UNAUTHENTICATED_TRAINING") == "1"
MAX_KNOWLEDGE_BATCH = 500
DATA_DIR = os.environ.get("CHIT_DATA_DIR", "data")
SESSIONS_DB = os.environ.get("CHIT_SESSIONS_DB", "data/sessions.db")
SESSION_TTL_DAYS = float(os.environ.get("CHIT_SESSION_TTL_DAYS", "30"))
MAX_SESSION_TURNS = int(os.environ.get("CHIT_MAX_SESSION_TURNS", "200"))
HISTORY_TURNS = int(os.environ.get("CHIT_HISTORY_TURNS", "8"))
SESSION_ID = re.compile(r"^[0-9a-f]{32}$")

_state: dict = {"runtime": None, "bridge": None, "error": None, "jobs": None, "memory": None, "knowledge": None, "sessions": None, "summarizer": None, "inference": None}
_data_lock = threading.Lock()  # one data split at a time
INFERENCE_QUEUE_SIZE = int(os.environ.get("CHIT_INFERENCE_QUEUE_SIZE", "32"))
INFERENCE_QUEUE_TIMEOUT = float(os.environ.get("CHIT_INFERENCE_QUEUE_TIMEOUT", "30"))


def _load_served_model() -> None:
    if not Path(CHECKPOINT).exists():
        _state.update(runtime=None, bridge=None, error=f"checkpoint not found: {CHECKPOINT} (train first)")
        return
    try:
        manifest_path = Path(CHECKPOINT).parent / "champion.json"
        if manifest_path.exists():
            champion = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected = champion.get("current", {}).get("sha256")
            if expected:
                from .promotion_state import file_sha256
                actual = file_sha256(Path(CHECKPOINT))
                if actual != expected:
                    raise ValueError("served checkpoint hash does not match champion manifest")
        rt = ChitRuntime.from_checkpoint(CHECKPOINT, memory=_state["memory"])
        _state.update(runtime=rt, bridge=Bridge(rt), error=None)
    except Exception as e:  # bad/incompatible checkpoint: stay up, report via /health
        log.exception("could not load %s", CHECKPOINT)
        _state.update(runtime=None, bridge=None, error=f"{type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    inference = InferenceManager(INFERENCE_QUEUE_SIZE, INFERENCE_QUEUE_TIMEOUT)
    await inference.start()
    memory_db = MEMORY_DB or str(Path(MEMORY_PATH).with_suffix(".db"))
    embedding_provider = None
    if EMBEDDING_MODEL_PATH:
        try:
            embedding_provider = SentenceTransformerProvider(
                EMBEDDING_MODEL_PATH, model_version=EMBEDDING_MODEL_VERSION)
        except Exception:
            log.exception("could not load local embedding model; using keyword retrieval")
    threshold = float(EMBEDDING_SEMANTIC_THRESHOLD) if EMBEDDING_SEMANTIC_THRESHOLD else None
    memory = SQLiteMemoryStore(memory_db, seed_path=None,
                               embedding_provider=embedding_provider, semantic_threshold=threshold)
    legacy_memory = Path(MEMORY_PATH)
    if Path(memory_db).resolve() == legacy_memory.resolve():
        raise RuntimeError("CHIT_MEMORY_DB and CHIT_MEMORY_PATH must point to different files")
    if memory.count() == 0:
        if legacy_memory.exists():
            backup = legacy_memory.with_name(f"{legacy_memory.name}.pre-sqlite")
            if not backup.exists():
                shutil.copy2(legacy_memory, backup)
            memory.import_json(legacy_memory)
        elif Path("data/memory_seed.json").exists():
            memory.import_json("data/memory_seed.json")
    sessions = SessionStore(SESSIONS_DB, max_turns=MAX_SESSION_TURNS)
    summarizer = SessionSummaryWorker(sessions)
    for pending_session in sessions.pending_summary_sessions():
        summarizer.submit(pending_session)
    _state.update(runtime=None, bridge=None, error=None, jobs=None,
                  memory=memory, knowledge=KnowledgeStore(KNOWLEDGE_DB),
                  sessions=sessions, summarizer=summarizer, inference=inference)
    if SESSION_TTL_DAYS > 0:
        removed = _state["sessions"].prune(SESSION_TTL_DAYS)
        if removed:
            log.info("pruned %d session(s) idle for more than %g days", removed, SESSION_TTL_DAYS)
    try:
        recovered = recover_promotion(Path(CHECKPOINT))
        if recovered:
            log.warning("resolved interrupted checkpoint transaction: %s", recovered["state"])
    except Exception:
        log.exception("failed to recover checkpoint promotion transaction")
        raise
    _load_served_model()
    # Training always writes a candidate. Promotion is a separate evaluated
    # operator action; the serving process never auto-installs raw job output.
    _state["jobs"] = TrainingJobManager(JOBS_DIR)
    try:
        yield
    finally:
        _state["jobs"].shutdown()
        summarizer.close()
        await inference.close()


app = FastAPI(title="Chit API", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def request_observability(request, call_next):
    request_id = request.headers.get("X-Request-ID", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", request_id):
        request_id = uuid.uuid4().hex
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        log.info(json.dumps({"event": "http_request", "request_id": request_id,
                             "method": request.method, "path": request.url.path,
                             "status_code": status,
                             "duration_ms": round((time.perf_counter() - started) * 1000, 3)},
                            separators=(",", ":")))


# --------------------------------------------------------------------------- auth & deps
def require_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and not (x_api_key and secrets.compare_digest(x_api_key, API_KEY)):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def require_training_access(x_api_key: str | None = Header(default=None)):
    # Training and knowledge change what the served model will say, so they are
    # never open by accident: without an API key they must be enabled explicitly.
    if not API_KEY and not ALLOW_UNAUTHENTICATED_TRAINING:
        raise HTTPException(status_code=403, detail="training API disabled: set CHIT_API_KEY "
                            "(or CHIT_ALLOW_UNAUTHENTICATED_TRAINING=1 for local development)")
    require_key(x_api_key)


def get_runtime() -> ChitRuntime:
    if _state["runtime"] is None:
        raise HTTPException(status_code=503, detail=_state["error"] or "model not loaded")
    return _state["runtime"]


def get_memory() -> SQLiteMemoryStore:
    if _state["memory"] is None:
        raise HTTPException(status_code=503, detail="memory not initialised")
    return _state["memory"]


def get_knowledge() -> KnowledgeStore:
    if _state["knowledge"] is None:
        raise HTTPException(status_code=503, detail="knowledge store not initialised")
    return _state["knowledge"]


def get_sessions() -> SessionStore:
    if _state["sessions"] is None:
        raise HTTPException(status_code=503, detail="session store not initialised")
    return _state["sessions"]


def get_jobs() -> TrainingJobManager:
    if _state["jobs"] is None:
        raise HTTPException(status_code=503, detail="training service not started")
    return _state["jobs"]


# --------------------------------------------------------------------------- inference & memory


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=2000)
    mode: Literal["assistant", "continue"] = Field(
        default="assistant",
        description="assistant formats the request with memory; continue preserves raw text continuation")
    tokens: int = Field(default=100, ge=1, le=500)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="0 = greedy")
    top_k: int = Field(default=50, ge=1, le=256)
    stop: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(default_factory=list, max_length=8)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    task: str = Field(default="chat", max_length=50, description='"chat" formats a request; "continue" performs raw text continuation')
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="default: the Bridge's own (0.7)")
    tokens: int | None = Field(default=None, ge=1, le=500,
                               description="maximum new tokens; byte-tokenizer models use one token per UTF-8 byte")
    session_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$", description=(
        "continue this conversation; omit to start a new one (its id is returned)"))


Tag = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[\w.:/-]+$")]


class MemoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2000)
    memory_type: str = Field(default="experience", max_length=50)
    importance: float = Field(default=0.5, ge=0, le=1)
    tags: list[Tag] = Field(default_factory=list, max_length=20)


@app.get("/health")
def health():
    jobs = _state["jobs"]
    return {"status": "ok" if _state["runtime"] else "no_model",
            "version": __version__,
            "model_loaded": _state["runtime"] is not None,
            "error": _state["error"],
            "training_job": jobs.active_id() if jobs else None,
            "inference": _state["inference"].stats if _state["inference"] else None,
            "memory_search": _memory_search_status()}


def _memory_search_status() -> dict | None:
    memory = _state["memory"]
    if memory is None:
        return None
    try:
        return memory.embedding_status()
    except Exception as exc:
        log.exception("could not read memory-store status")
        return {"mode": "unavailable", "error": type(exc).__name__}


@app.get("/ready", dependencies=[Depends(require_key)])
def readiness():
    memory_status = _memory_search_status()
    checks = {"model": _state["runtime"] is not None,
              "memory": bool(memory_status and memory_status.get("mode") != "unavailable"),
              "knowledge": _state["knowledge"] is not None, "sessions": _state["sessions"] is not None,
              "inference": bool(_state["inference"] and _state["inference"].stats["accepting"])}
    body = {"status": "ready" if all(checks.values()) else "not_ready", "checks": checks,
            "error": _state["error"]}
    if not all(checks.values()):
        return JSONResponse(content=body, status_code=503)
    return body


@app.get("/model", dependencies=[Depends(require_key)])
def model_info():
    rt = get_runtime()
    return {"model_config": rt.model_config, "parameters": rt.model.num_parameters(),
            "device": str(rt.device), "checkpoint": rt.checkpoint_meta,
            "tokenizer": {"name": rt.tokenizer.name, "vocab_size": rt.tokenizer.vocab_size,
                          "sha256": getattr(rt.tokenizer, "asset_sha256", None)},
            "memory_search": _memory_search_status(),
            "inference": {"queue_capacity": INFERENCE_QUEUE_SIZE,
                          "queue_timeout_seconds": INFERENCE_QUEUE_TIMEOUT,
                          "batching": False}}


@app.post("/generate", dependencies=[Depends(require_key)])
async def generate(r: GenerateRequest):
    get_runtime()
    bridge = _state["bridge"]
    try:
        if r.mode == "continue":
            runtime = _state["runtime"]
            text = await _state["inference"].run(
                lambda: runtime.generate(r.prompt, r.tokens, r.temperature, r.top_k, stop=r.stop))
        else:
            decision = await _state["inference"].run(lambda: bridge.process(
                Context(user_input=r.prompt, task="chat"), r.temperature,
                max_new_tokens=r.tokens, top_k=r.top_k, stop=r.stop or None))
            text = decision.text
    except InferenceOverloaded as exc:
        raise HTTPException(status_code=429, detail={"code": "inference_overloaded", "message": str(exc)},
                            headers={"Retry-After": "1"}) from exc
    return {"text": text}


@app.post("/chat", dependencies=[Depends(require_key)])
async def chat(r: ChatRequest):
    get_runtime()
    sessions = get_sessions()
    use_session = r.task != "continue"  # a plain-text continuation has no conversation to remember
    if not use_session and r.session_id:
        raise HTTPException(status_code=422, detail=["sessions are not used with task 'continue'"])
    history: list[dict] = []
    session_context = None
    if use_session and r.session_id:
        try:
            session_context = sessions.get(r.session_id)
            history = sessions.history(r.session_id, HISTORY_TURNS)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="session not found")
    bridge = _state["bridge"]
    try:
        d = await _state["inference"].run(lambda: bridge.process(
            Context(user_input=r.message, task=r.task, history=history,
                    facts=(session_context["facts"] if session_context and session_context["facts_enabled"] else []),
                    summary=(session_context["summary"] if session_context and
                             session_context["summary_enabled"] else "")),
            r.temperature, max_new_tokens=r.tokens))
    except InferenceOverloaded as exc:
        raise HTTPException(status_code=429, detail={"code": "inference_overloaded", "message": str(exc)},
                            headers={"Retry-After": "1"}) from exc
    session_id = None
    if use_session:
        try:
            session_id = r.session_id or sessions.create()["id"]
            sessions.append(session_id, [("user", r.message), ("assistant", d.text)])
            if sessions.summary_needed(session_id):
                _state["summarizer"].submit(session_id)
        except SessionNotFound:  # deleted while the reply was being generated
            raise HTTPException(status_code=404, detail="session not found")
    return {"text": d.text, "session_id": session_id, "metadata": d.metadata}


# --------------------------------------------------------------------------- sessions


def _session_or_404(session_id: str) -> dict:
    if not SESSION_ID.match(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    try:
        return get_sessions().get(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found")


@app.post("/sessions", status_code=201, dependencies=[Depends(require_key)])
def create_session():
    """Start an empty conversation. (POST /chat without a session_id also starts one.)"""
    return get_sessions().create()


@app.get("/sessions", dependencies=[Depends(require_key)])
def list_sessions(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    items, total = get_sessions().list(limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "sessions": items}


@app.get("/sessions/{session_id}", dependencies=[Depends(require_key)])
def get_session(session_id: str, limit: int | None = Query(default=None, ge=1, le=1000)):
    session = _session_or_404(session_id)
    return {**session, "messages": get_sessions().history(session_id, limit)}


class SessionFactsSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class SessionSummarySetting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@app.get("/sessions/{session_id}/facts", dependencies=[Depends(require_key)])
def get_session_facts(session_id: str):
    _session_or_404(session_id)
    return get_sessions().facts(session_id)


@app.patch("/sessions/{session_id}/facts", dependencies=[Depends(require_key)])
def configure_session_facts(session_id: str, setting: SessionFactsSetting):
    _session_or_404(session_id)
    return get_sessions().set_facts_enabled(session_id, setting.enabled)


@app.post("/sessions/{session_id}/facts/refresh", dependencies=[Depends(require_key)])
def refresh_session_facts(session_id: str):
    _session_or_404(session_id)
    try:
        return get_sessions().refresh_facts(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/sessions/{session_id}/facts", dependencies=[Depends(require_key)])
def clear_session_facts(session_id: str):
    _session_or_404(session_id)
    return get_sessions().clear_facts(session_id)


@app.get("/sessions/{session_id}/summary", dependencies=[Depends(require_key)])
def get_session_summary(session_id: str):
    session = _session_or_404(session_id)
    return {"session_id": session_id, "enabled": session["summary_enabled"],
            "summary": session["summary"], "status": session["summary_status"],
            "error": session["summary_error"], "through_turn_seq": session["summary_through_seq"],
            "updated_at": session["context_updated_at"]}


@app.patch("/sessions/{session_id}/summary", dependencies=[Depends(require_key)])
def configure_session_summary(session_id: str, setting: SessionSummarySetting):
    try:
        session = get_sessions().set_summary_enabled(session_id, setting.enabled)
        if setting.enabled and get_sessions().summary_needed(session_id):
            _state["summarizer"].submit(session_id)
        return {"session_id": session_id, "enabled": session["summary_enabled"],
                "summary": session["summary"], "status": session["summary_status"]}
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found")


@app.post("/sessions/{session_id}/summary/refresh", dependencies=[Depends(require_key)])
def refresh_session_summary(session_id: str):
    try:
        if not get_sessions().summary_needed(session_id):
            return get_session_summary(session_id)
        _state["summarizer"].submit(session_id)
        return {"session_id": session_id, "status": "pending"}
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found")


@app.delete("/sessions/{session_id}/summary", dependencies=[Depends(require_key)])
def clear_session_summary(session_id: str):
    try:
        session = get_sessions().clear_summary(session_id)
        return {"session_id": session_id, "summary": session["summary"],
                "status": session["summary_status"]}
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found")


@app.delete("/sessions/{session_id}", status_code=204, dependencies=[Depends(require_key)])
def delete_session(session_id: str):
    _session_or_404(session_id)
    get_sessions().delete(session_id)
    return Response(status_code=204)


@app.post("/memory", status_code=201, dependencies=[Depends(require_key)])
def add_memory(m: MemoryIn):
    return get_memory().add(m.content, m.memory_type, m.importance, m.tags)


@app.get("/memory/search", dependencies=[Depends(require_key)])
def search_memory(q: str = Query(min_length=1, max_length=200), limit: int = Query(5, ge=1, le=50)):
    return {"results": get_memory().search(q, limit)}


@app.delete("/memory/{memory_id}", status_code=204, dependencies=[Depends(require_key)])
def delete_memory(memory_id: str):
    if not get_memory().delete(memory_id):
        raise HTTPException(status_code=404, detail="memory not found")
    return Response(status_code=204)


# --------------------------------------------------------------------------- training


class ModelOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vocab_size: int | None = Field(default=None, ge=1, le=50_000)
    block_size: int | None = Field(default=None, ge=8, le=2048)
    n_layer: int | None = Field(default=None, ge=1, le=48)
    n_head: int | None = Field(default=None, ge=1, le=64)
    n_embd: int | None = Field(default=None, ge=8, le=4096)
    dropout: float | None = Field(default=None, ge=0.0, lt=1.0)
    position_encoding: Literal["absolute", "rope"] | None = None
    rope_theta: float | None = Field(default=None, gt=0)


class TrainingOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_size: int | None = Field(default=None, ge=1, le=1024)
    learning_rate: float | None = Field(default=None, gt=0.0, le=1.0)
    weight_decay: float | None = Field(default=None, ge=0.0, le=1.0)
    max_steps: int | None = Field(default=None, ge=1)
    eval_interval: int | None = Field(default=None, ge=1)
    eval_steps: int | None = Field(default=None, ge=1, le=1000)
    checkpoint_interval: int | None = Field(default=None, ge=1)
    grad_clip: float | None = Field(default=None, gt=0.0, le=100.0)
    warmup_steps: int | None = Field(default=None, ge=0)
    lr_schedule: Literal["constant", "cosine"] | None = None
    min_lr_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    context_curriculum: list[int] | None = None


InitMode = Literal["scratch", "current", "auto"]


class TrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: str = Field(default="chit_cpu_learning", pattern=r"^[A-Za-z0-9_-]{1,64}$",
                        description="name of a JSON file in CHIT_CONFIG_DIR, without .json")
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    device: Literal["auto", "cpu", "cuda"] | None = None
    init: InitMode = Field(default="scratch", description=(
        "scratch: random weights. current: fine-tune the served model (its architecture is used). "
        "auto: current if a compatible model is served, otherwise scratch."))
    model: ModelOverrides = Field(default_factory=ModelOverrides)
    training: TrainingOverrides = Field(default_factory=TrainingOverrides)
    promote: bool = Field(default=False, description="deprecated; candidates require evaluation and explicit promotion")
    force_promote: bool = Field(default=False, description="force-install this candidate after successful training, bypassing evaluation and reviewer gates")


def _overrides(m: BaseModel) -> dict:
    return {k: v for k, v in m.model_dump().items() if v is not None}


def build_config(r: TrainRequest, *, check_train_file: bool = True) -> ChitConfig:
    """Resolve a request into a ChitConfig (before init resolution), or raise HTTPException."""
    path = Path(CONFIG_DIR) / f"{r.config}.json"  # the name pattern rules out path traversal
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"config not found: {r.config}")
    try:
        base = load_config(path)
    except (ConfigError, OSError) as e:
        log.exception("config %s is invalid", path)
        raise HTTPException(status_code=500, detail=f"config {r.config} is invalid: {e}")
    try:
        return dataclasses.replace(
            base,
            seed=base.seed if r.seed is None else r.seed,
            device=r.device or base.device,
            model=dataclasses.replace(base.model, **_overrides(r.model)),
            training=dataclasses.replace(base.training, **_overrides(r.training)),
        )
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=[str(e)])


def resolve_init(r: TrainRequest, cfg: ChitConfig) -> tuple[ChitConfig, Path | None]:
    """Pick the starting weights. Fine-tuning takes the served model's architecture."""
    if r.init == "scratch":
        return cfg, None
    rt = _state["runtime"]
    served = rt.model_config if rt is not None and Path(CHECKPOINT).is_file() else None
    if served is None:
        if r.init == "current":
            raise HTTPException(status_code=422, detail=["init 'current' requested but no model is being served"])
        return cfg, None
    try:
        model = dataclasses.replace(ModelConfig(**served), **_overrides(r.model))
    except (ConfigError, TypeError) as e:
        raise HTTPException(status_code=422, detail=[f"served model config is unusable: {e}"])
    defaults = {"position_encoding": "absolute", "rope_theta": 10000.0}
    changed = [k for k in ARCHITECTURE_KEYS if getattr(model, k) != served.get(k, defaults.get(k))]
    if rt.tokenizer.name != cfg.tokenizer.name:
        changed.append("tokenizer")
    elif cfg.tokenizer.name != ByteTokenizer.name:
        try:
            candidate = create_tokenizer(cfg.tokenizer.name, cfg.tokenizer.model_file)
            if candidate.asset_sha256 != getattr(rt.tokenizer, "asset_sha256", None):
                changed.append("tokenizer assets")
        except (ValueError, RuntimeError, OSError):
            changed.append("tokenizer assets")
    if changed:
        if r.init == "current":
            raise HTTPException(status_code=422, detail=[
                f"init 'current' cannot change the architecture ({', '.join(changed)}); use init 'scratch'"])
        return cfg, None
    return dataclasses.replace(cfg, model=model), Path(CHECKPOINT)


def validate_config(cfg: ChitConfig) -> None:
    problems = []
    try:
        tokenizer = create_tokenizer(cfg.tokenizer.name, cfg.tokenizer.model_file)
        if cfg.model.vocab_size != tokenizer.vocab_size:
            problems.append(f"model.vocab_size must equal tokenizer vocab ({tokenizer.vocab_size})")
    except (ValueError, RuntimeError, OSError) as exc:
        problems.append(f"tokenizer configuration is unusable: {exc}")
        tokenizer = None
    if cfg.training.max_steps > MAX_TRAIN_STEPS:
        problems.append(f"training.max_steps must be <= {MAX_TRAIN_STEPS}")
    if cfg.device == "cuda" and not torch.cuda.is_available():
        problems.append("device 'cuda' requested but CUDA is not available on this server")
    data_files = [(f"data.{name}", Path(getattr(cfg.data, name)))
                  for name in ("train_file", "eval_file")]
    data_files.extend((f"data.sources[{i}].path", Path(source.path))
                      for i, source in enumerate(cfg.data.sources))
    for name, f in data_files:
        if not f.is_file():
            problems.append(f"{name} not found on server")
        elif f.stat().st_size <= cfg.model.block_size:
            problems.append(f"{name} must be larger than model.block_size")
        elif tokenizer is not None and tokenizer.name != ByteTokenizer.name:
            try:
                # Read a bounded prefix: validation only needs to establish that
                # the file has at least one complete model window.
                with f.open("r", encoding="utf-8") as source:
                    sample = source.read(256 * 1024)
                if len(tokenizer.encode(sample)) <= cfg.model.block_size:
                    problems.append(f"{name} must contain more than model.block_size tokens")
            except (UnicodeError, OSError) as exc:
                problems.append(f"{name} cannot be tokenized: {exc}")
    if problems:
        raise HTTPException(status_code=422, detail=problems)


def _snapshot_init(init: Path | None, job_dir: Path) -> Path | None:
    """Copy the starting checkpoint into the job, so the run is reproducible later."""
    if init is None:
        return None
    job_dir.mkdir(parents=True, exist_ok=True)
    dst = job_dir / "init.pt"
    shutil.copyfile(init, dst)
    return dst


def _submit(cfg: ChitConfig, r: TrainRequest, job_id: str, init: Path | None, **kw) -> dict:
    if r.promote and not r.force_promote:
        raise HTTPException(status_code=422, detail=(
            "direct training promotion is disabled; evaluate the candidate with eval_runner.py "
            "and promote it with promote_candidate.py after it passes the reviewed gates; "
            "set force_promote=true to bypass those gates"))
    try:
        callback = kw.pop("after_success", None)
        metadata = dict(kw.pop("metadata", {}) or {})
        metadata["force_promote"] = r.force_promote
        if r.force_promote:
            def after_success(snapshot: dict) -> None:
                _force_promote_candidate(snapshot)
                snapshot["promoted"] = True
                if callback:
                    callback(snapshot)
        else:
            after_success = callback
        return get_jobs().submit(cfg, promote=r.force_promote, job_id=job_id,
                                 init_checkpoint=init, metadata=metadata,
                                 after_success=after_success, **kw)
    except JobConflict as e:
        raise HTTPException(status_code=409, detail={"message": str(e), "active_job": e.active_id})


def _force_promote_candidate(snapshot: dict) -> None:
    """Install a successfully trained candidate without evaluation/reviewer gates."""
    import shutil
    from datetime import datetime, timezone
    from .promotion_state import file_sha256, install_checkpoint

    candidate = Path(snapshot["checkpoint"])
    target = Path(CHECKPOINT)
    # Load first so a corrupt/incompatible checkpoint cannot replace the live file.
    candidate_runtime = ChitRuntime.from_checkpoint(candidate, memory=_state["memory"])
    current_runtime = _state.get("runtime")
    if current_runtime and candidate_runtime.tokenizer.name != current_runtime.tokenizer.name:
        raise ValueError("force promotion does not bypass tokenizer compatibility")
    target.parent.mkdir(parents=True, exist_ok=True)
    archive = target.parent / "champions"
    archive.mkdir(exist_ok=True)
    old_hash, candidate_hash = file_sha256(target), file_sha256(candidate)
    old_archive, new_archive = archive / f"{old_hash}.pt", archive / f"{candidate_hash}.pt"
    if not old_archive.exists():
        shutil.copy2(target, old_archive)
    if not new_archive.exists():
        shutil.copy2(candidate, new_archive)
    manifest_path = target.parent / "champion.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    now = datetime.now(timezone.utc).isoformat()
    manifest = {"schema_version": 1, "updated_at": now,
                "current": {"sha256": candidate_hash, "checkpoint": str(new_archive),
                            "evaluation": snapshot.get("final_evaluation")},
                "previous": {"sha256": old_hash, "checkpoint": str(old_archive)},
                "decision": {"mode": "forced_training_promotion", "evaluation_gates_bypassed": True},
                "history": previous.get("history", []) + [{"at": now, "from": old_hash,
                    "to": candidate_hash, "reason": "explicit force_promote API option"}]}
    install_checkpoint(target, new_archive, source_sha256=candidate_hash,
                       previous_sha256=old_hash, previous_archive=old_archive, manifest=manifest)
    _state.update(runtime=candidate_runtime, bridge=Bridge(candidate_runtime), error=None)


def _ensure_idle() -> None:
    active = get_jobs().active_id()
    if active:
        raise HTTPException(status_code=409, detail={"message": f"training job {active} is already active",
                                                     "active_job": active})


@app.get("/train/configs", dependencies=[Depends(require_training_access)])
def list_train_configs():
    return {"configs": sorted(p.stem for p in Path(CONFIG_DIR).glob("*.json"))}


@app.post("/train", status_code=202, dependencies=[Depends(require_training_access)])
def start_training(r: TrainRequest, response: Response):
    cfg, init = resolve_init(r, build_config(r))
    validate_config(cfg)
    _ensure_idle()
    job_id = uuid.uuid4().hex
    job_dir = Path(JOBS_DIR) / job_id
    try:
        job = _submit(cfg, r, job_id, _snapshot_init(init, job_dir), metadata={"init": r.init})
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    response.headers["Location"] = f"/train/{job['id']}"
    return job


@app.get("/train", dependencies=[Depends(require_training_access)])
def list_training_jobs():
    return {"jobs": get_jobs().list()}


@app.get("/train/{job_id}", dependencies=[Depends(require_training_access)])
def get_training_job(job_id: str):
    try:
        return get_jobs().get(job_id)
    except JobNotFound:
        raise HTTPException(status_code=404, detail="training job not found")


@app.post("/train/{job_id}/cancel", status_code=202, dependencies=[Depends(require_training_access)])
def cancel_training_job(job_id: str):
    try:
        return get_jobs().cancel(job_id)
    except JobNotFound:
        raise HTTPException(status_code=404, detail="training job not found")
    except JobFinished as e:
        raise HTTPException(status_code=409, detail=str(e))


# --------------------------------------------------------------------------- knowledge


class _KnowledgeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    source: str | None = Field(default=None, max_length=200, description="where this came from, for audit")
    remember: bool = Field(default=False, description=(
        "also store it in memory, so /chat can use it immediately, before any training"))


class TextKnowledge(_KnowledgeBase):
    kind: Literal["text"]
    text: str = Field(min_length=1, max_length=20_000)


class QAKnowledge(_KnowledgeBase):
    kind: Literal["qa"]
    question: str = Field(min_length=1, max_length=2_000)
    answer: str = Field(min_length=1, max_length=5_000)


class ReasoningKnowledge(_KnowledgeBase):
    kind: Literal["reasoning"]
    input: str = Field(min_length=1, max_length=5_000)
    reasoning: str = Field(min_length=1, max_length=10_000)
    answer: str = Field(min_length=1, max_length=5_000)


KnowledgeItem = Annotated[Union[TextKnowledge, QAKnowledge, ReasoningKnowledge], Field(discriminator="kind")]
_PAYLOAD_FIELDS = {"text": ("text",), "qa": ("question", "answer"), "reasoning": ("input", "reasoning", "answer")}


class KnowledgeBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[KnowledgeItem] = Field(min_length=1, max_length=MAX_KNOWLEDGE_BATCH)


def _memory_text(item) -> str:
    if item.kind == "qa":
        return f"{item.question.strip()} {item.answer.strip()}"
    if item.kind == "reasoning":
        return f"{item.input.strip()} {item.answer.strip()}"
    return item.text.strip()


@app.post("/knowledge", status_code=201, dependencies=[Depends(require_training_access)])
def add_knowledge(batch: KnowledgeBatch):
    """Teach Chit: queue knowledge for the next training run (all items or none)."""
    rows = [{"kind": it.kind, "payload": {f: getattr(it, f) for f in _PAYLOAD_FIELDS[it.kind]},
             "tags": it.tags, "source": it.source} for it in batch.items]
    try:
        results = get_knowledge().add_many(rows)
    except KnowledgeError as e:
        raise HTTPException(status_code=422, detail=[str(e)])
    out = []
    for it, res in zip(batch.items, results):
        entry = {**res.entry, "created": res.created, "memory_id": None}
        if it.remember and res.created:
            try:
                entry["memory_id"] = get_memory().add(
                    _memory_text(it)[:2000], "knowledge", 0.7, it.tags, source=f"knowledge:{res.entry['id']}")["id"]
            except (OSError, ValueError):  # knowledge is stored; memory is a convenience
                log.exception("could not mirror knowledge %s into memory", res.entry["id"])
        out.append(entry)
    created = sum(r.created for r in results)
    return {"created": created, "duplicates": len(results) - created, "items": out}


@app.get("/knowledge", dependencies=[Depends(require_training_access)])
def list_knowledge(status: Literal["pending", "trained"] | None = None,
                   kind: Literal["text", "qa", "reasoning"] | None = None,
                   tag: list[str] = Query(default_factory=list, max_length=10),
                   limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    items, total = get_knowledge().list(status, kind, tag, limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/knowledge/stats", dependencies=[Depends(require_training_access)])
def knowledge_stats():
    return get_knowledge().stats()


@app.get("/knowledge/{entry_id}", dependencies=[Depends(require_training_access)])
def get_knowledge_entry(entry_id: str):
    entry = get_knowledge().get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="knowledge entry not found")
    return entry


@app.delete("/knowledge/{entry_id}", status_code=204, dependencies=[Depends(require_training_access)])
def delete_knowledge_entry(entry_id: str):
    """Remove an entry from future training. A model already trained on it keeps what it
    learned until it is retrained with init 'scratch'."""
    if not get_knowledge().delete(entry_id):
        raise HTTPException(status_code=404, detail="knowledge entry not found")
    return Response(status_code=204)


class KnowledgeTrainRequest(TrainRequest):
    init: InitMode = "auto"
    select: Literal["all", "pending"] = Field(default="all", description=(
        "all: every entry (recommended; limits forgetting). pending: only entries not yet trained."))
    tags: list[Tag] = Field(default_factory=list, max_length=10, description="only entries with all these tags")
    include_base: bool = Field(default=True, description="mix in the config's train_file corpus")
    repeat: int = Field(default=3, ge=1, le=100, description="times the knowledge appears in the dataset")


@app.post("/knowledge/train", status_code=202, dependencies=[Depends(require_training_access)])
def train_on_knowledge(r: KnowledgeTrainRequest, response: Response):
    """Train on the stored knowledge now. Entries become 'trained' when the run is promoted."""
    cfg, init = resolve_init(r, build_config(r))
    _ensure_idle()  # fail fast, before writing a dataset
    store = get_knowledge()
    entries = store.select(status="pending" if r.select == "pending" else None, tags=r.tags)
    if not entries:
        raise HTTPException(status_code=422, detail=["no knowledge matches this request; add some with POST /knowledge"])

    job_id = uuid.uuid4().hex
    job_dir = Path(JOBS_DIR) / job_id
    try:
        base_text = ""
        if r.include_base:
            base = Path(cfg.data.train_file)
            if not base.is_file():
                raise HTTPException(status_code=422, detail=["data.train_file not found on server"])
            base_text = base.read_text(encoding="utf-8")
        try:
            ds = build_dataset(entries, job_dir / "dataset", base_text=base_text, repeat=r.repeat,
                               max_bytes=MAX_DATASET_BYTES)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=[str(e)])
        # Preserve source-aware curricula while adding the knowledge dataset as
        # its own stream. Without this, train() would prefer the configured
        # sources and silently ignore the generated knowledge file.
        sources = ([*cfg.data.sources, DataSourceConfig(path=str(ds.train_file), weight=1.0)]
                   if cfg.data.sources else [])
        cfg = dataclasses.replace(cfg, data=dataclasses.replace(
            cfg.data, train_file=str(ds.train_file), sources=sources))
        validate_config(cfg)

        ids = ds.entry_ids

        def mark_trained(snapshot: dict) -> None:
            if snapshot["promoted"]:
                store.mark_trained(ids, snapshot["id"])

        meta = {"init": r.init, "knowledge": {
            "entries": len(ids), "select": r.select, "tags": r.tags, "repeat": r.repeat,
            "include_base": r.include_base, "dataset_bytes": ds.size_bytes, "dataset_sha256": ds.sha256,
            "manifest": str(ds.manifest_file)}}
        job = _submit(cfg, r, job_id, _snapshot_init(init, job_dir), metadata=meta, after_success=mark_trained)
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    response.headers["Location"] = f"/train/{job['id']}"
    return job


# --------------------------------------------------------------------------- training data


class SplitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$", description=(
        "name of a text file inside CHIT_DATA_DIR (for example a mounted corpus.txt); no folders"))
    config: str = Field(default="chit_cpu_learning", pattern=r"^[A-Za-z0-9_-]{1,64}$", description=(
        "the config whose data.train_file / data.eval_file are written and whose block_size is checked"))
    by: Literal["line", "paragraph"] = Field(default="line", description=(
        "paragraph keeps blocks separated by blank lines together, e.g. User:/Chit: pairs"))
    eval_fraction: float = Field(default=0.1, gt=0, lt=0.5)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    overwrite: bool = Field(default=False, description="replace existing train/eval files (old ones are kept as .bak)")
    dry_run: bool = Field(default=False, description="report what would be written and write nothing")


def _data_paths(config: str) -> tuple[ChitConfig, Path, Path]:
    cfg = build_config(TrainRequest(config=config))
    return cfg, Path(cfg.data.train_file), Path(cfg.data.eval_file)


def _resolve_source(name: str) -> Path:
    root = Path(DATA_DIR).resolve()
    path = (root / name).resolve()  # follows symlinks, so a link pointing outside is caught below
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail=f"source not found in the data folder: {name}")
    if path.stat().st_size > MAX_DATASET_BYTES:
        raise HTTPException(status_code=422, detail=[f"source is larger than the {MAX_DATASET_BYTES} byte limit"])
    return path


@app.get("/data", dependencies=[Depends(require_training_access)])
def data_status(config: str = Query("chit_cpu_learning", pattern=r"^[A-Za-z0-9_-]{1,64}$")):
    """What is on the server right now: the config's train/eval files, checks, and splittable sources.

    Use it after mounting or editing files, before training.
    """
    cfg, train_path, eval_path = _data_paths(config)
    report = datasets.analyze(train_path, eval_path, cfg.model.block_size, MAX_DATASET_BYTES)
    training_sources = []
    source_warnings = []
    for i, source in enumerate(cfg.data.sources):
        info = datasets.file_info(source.path)
        ready = bool(info and info["bytes"] > cfg.model.block_size)
        training_sources.append({"weight": source.weight, "file": info,
                                 "ready": ready, "missing_path": source.path if info is None else None})
        if not ready:
            source_warnings.append(
                f"data.sources[{i}] is missing or not larger than model.block_size ({cfg.model.block_size} bytes): "
                f"{source.path}")
    if source_warnings:
        report["warnings"].extend(source_warnings)
        report["ready_to_train"] = False
    return {"config": config, "block_size": cfg.model.block_size, **report,
            "training_sources": training_sources,
            "sources": datasets.list_sources(DATA_DIR)}


@app.post("/data/split", dependencies=[Depends(require_training_access)])
def split_data(r: SplitRequest):
    """Split a corpus file from the data folder into the config's train and eval files."""
    cfg, train_path, eval_path = _data_paths(r.config)
    if cfg.data.sources:
        raise HTTPException(status_code=422, detail=[
            "this config trains from data.sources; split each configured source separately instead of writing train_file"])
    source = _resolve_source(r.source)
    _ensure_idle()
    try:
        text = source.read_text(encoding="utf-8")
        res = datasets.split_corpus(text, r.by, r.eval_fraction, r.seed)
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail=["source must be UTF-8 text"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=[str(e)])

    train_text, eval_text = datasets.join_items(res.train, r.by), datasets.join_items(res.eval, r.by)
    train_bytes, eval_bytes = len(train_text.encode("utf-8")), len(eval_text.encode("utf-8"))
    block = cfg.model.block_size
    problems = [f"the {name} file would be {n} bytes; it must be larger than model.block_size ({block})"
                for name, n in (("train", train_bytes), ("eval", eval_bytes)) if n <= block]
    if problems:
        raise HTTPException(status_code=422, detail=problems + ["add more text or raise eval_fraction"])

    existing = [p for p in (train_path, eval_path) if p.exists()]
    report = {
        "source": r.source, "config": r.config, "by": r.by, "seed": r.seed,
        "duplicates_removed": res.duplicates_removed,
        "train": {"path": str(train_path), "items": len(res.train), "bytes": train_bytes},
        "eval": {"path": str(eval_path), "items": len(res.eval), "bytes": eval_bytes},
        "would_overwrite": [str(p) for p in existing],
        "warnings": ([f"eval is under {datasets.MIN_USEFUL_EVAL_BYTES} bytes, so the eval loss will be noisy"]
                     if eval_bytes < datasets.MIN_USEFUL_EVAL_BYTES else []),
    }
    if r.dry_run:
        return {**report, "written": False, "backups": []}
    if existing and not r.overwrite:
        raise HTTPException(status_code=409, detail={
            "message": "train/eval files already exist; send overwrite=true to replace them (the old files are kept as .bak)",
            "existing": [str(p) for p in existing]})

    with _data_lock:
        _ensure_idle()
        try:
            backups = [b for b in (datasets.backup(p) for p in existing) if b]
            datasets.write_text(train_path, train_text)
            datasets.write_text(eval_path, eval_text)
        except OSError as e:
            log.exception("could not write training data")
            raise HTTPException(status_code=500, detail=f"could not write {e.filename or 'the data files'}: "
                                                        f"{e.strerror or e} (is the folder mounted read-only?)")
    return {**report, "written": True, "backups": backups}
