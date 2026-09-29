"""Chit HTTP API.

Run from the repo root:
    uvicorn pranav.chit.api:app --host 127.0.0.1 --port 8000

Environment variables:
    CHIT_CHECKPOINT  path to checkpoint   (default: checkpoints/latest.pt)
    CHIT_API_KEY     if set, every request except /health must send
                     the header  X-API-Key: <value>

    Training API (see docs/TRAINING_API.md):
    CHIT_CONFIG_DIR       directory of training configs     (default: configs)
    CHIT_JOBS_DIR         per-job training output           (default: checkpoints/jobs)
    CHIT_MAX_TRAIN_STEPS  upper bound for training.max_steps (default: 100000)
    CHIT_ALLOW_UNAUTHENTICATED_TRAINING
                          "1" enables /train without CHIT_API_KEY (local dev only)

Run with a single worker (the default). Model state and the training job
registry live in this process, so --workers N would give each worker its own
model and allow N concurrent training runs.
"""
import dataclasses
import logging
import os
import secrets
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import torch
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from .bridge import Bridge, Context
from .config import ChitConfig, load_config
from .jobs import JobConflict, JobFinished, JobNotFound, TrainingJobManager
from .runtime import ChitRuntime
from .tokenizer import ByteTokenizer

log = logging.getLogger(__name__)

CHECKPOINT = os.environ.get("CHIT_CHECKPOINT", "checkpoints/latest.pt")
API_KEY = os.environ.get("CHIT_API_KEY")
CONFIG_DIR = os.environ.get("CHIT_CONFIG_DIR", "configs")
JOBS_DIR = os.environ.get("CHIT_JOBS_DIR", "checkpoints/jobs")
MAX_TRAIN_STEPS = int(os.environ.get("CHIT_MAX_TRAIN_STEPS", "100000"))
ALLOW_UNAUTHENTICATED_TRAINING = os.environ.get("CHIT_ALLOW_UNAUTHENTICATED_TRAINING") == "1"

_state = {"runtime": None, "bridge": None, "error": None, "jobs": None}
_lock = threading.Lock()  # one generation at a time; the model is not built for parallel calls


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state.update(runtime=None, bridge=None, error=None, jobs=None)
    if Path(CHECKPOINT).exists():
        try:
            rt = ChitRuntime.from_checkpoint(CHECKPOINT)
            _state.update(runtime=rt, bridge=Bridge(rt), error=None)
        except Exception as e:  # bad/incompatible checkpoint: stay up, report via /health
            _state["error"] = f"{type(e).__name__}: {e}"
    else:
        _state["error"] = f"checkpoint not found: {CHECKPOINT} (train first)"
    _state["jobs"] = TrainingJobManager(JOBS_DIR, on_success=promote_checkpoint)
    try:
        yield
    finally:
        _state["jobs"].shutdown()


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
    jobs = _state["jobs"]
    return {"status": "ok" if _state["runtime"] else "no_model",
            "model_loaded": _state["runtime"] is not None,
            "error": _state["error"],
            "training_job": jobs.active_id() if jobs else None}


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


# --------------------------------------------------------------------------- training


def promote_checkpoint(job_checkpoint: Path) -> None:
    """Make a finished job's checkpoint the served model.

    The checkpoint is loaded first, so a file that cannot be served is never
    promoted. It is then copied over CHECKPOINT atomically and swapped in under
    the generation lock, so no request ever sees a half-loaded model.
    """
    rt = ChitRuntime.from_checkpoint(job_checkpoint)
    target = Path(CHECKPOINT)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    try:
        shutil.copyfile(job_checkpoint, tmp)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
    with _lock:
        _state.update(runtime=rt, bridge=Bridge(rt), error=None)
    log.info("promoted %s -> %s and reloaded the model", job_checkpoint, target)


def require_training_access(x_api_key: str | None = Header(default=None)):
    # Training is expensive and replaces the served model, so it is never open
    # by accident: without an API key it must be enabled explicitly.
    if not API_KEY and not ALLOW_UNAUTHENTICATED_TRAINING:
        raise HTTPException(status_code=403, detail="training API disabled: set CHIT_API_KEY "
                            "(or CHIT_ALLOW_UNAUTHENTICATED_TRAINING=1 for local development)")
    require_key(x_api_key)


def get_jobs() -> TrainingJobManager:
    if _state["jobs"] is None:
        raise HTTPException(status_code=503, detail="training service not started")
    return _state["jobs"]


class ModelOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_size: int | None = Field(default=None, ge=8, le=2048)
    n_layer: int | None = Field(default=None, ge=1, le=48)
    n_head: int | None = Field(default=None, ge=1, le=64)
    n_embd: int | None = Field(default=None, ge=8, le=4096)
    dropout: float | None = Field(default=None, ge=0.0, lt=1.0)


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


class TrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: str = Field(default="chit_cpu_learning", pattern=r"^[A-Za-z0-9_-]{1,64}$",
                        description="name of a JSON file in CHIT_CONFIG_DIR, without .json")
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    device: Literal["auto", "cpu", "cuda"] | None = None
    model: ModelOverrides = Field(default_factory=ModelOverrides)
    training: TrainingOverrides = Field(default_factory=TrainingOverrides)
    promote: bool = Field(default=True, description="serve the new model when training succeeds")


def _overrides(m: BaseModel) -> dict:
    return {k: v for k, v in m.model_dump().items() if v is not None}


def build_config(r: TrainRequest) -> ChitConfig:
    """Resolve a request into a validated ChitConfig, or raise HTTPException."""
    path = Path(CONFIG_DIR) / f"{r.config}.json"  # the name pattern rules out path traversal
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"config not found: {r.config}")
    try:
        base = load_config(path)
    except (ValueError, TypeError, OSError) as e:
        log.exception("config %s is invalid", path)
        raise HTTPException(status_code=500, detail=f"config {r.config} is invalid: {e}")

    cfg = dataclasses.replace(
        base,
        seed=base.seed if r.seed is None else r.seed,
        device=r.device or base.device,
        model=dataclasses.replace(base.model, **_overrides(r.model)),
        training=dataclasses.replace(base.training, **_overrides(r.training)),
    )

    problems = []
    if cfg.model.n_embd % cfg.model.n_head:
        problems.append(f"model.n_embd ({cfg.model.n_embd}) must be divisible by model.n_head ({cfg.model.n_head})")
    if cfg.model.vocab_size != ByteTokenizer.vocab_size:
        problems.append(f"model.vocab_size must be {ByteTokenizer.vocab_size} (byte tokenizer)")
    if cfg.training.max_steps > MAX_TRAIN_STEPS:
        problems.append(f"training.max_steps must be <= {MAX_TRAIN_STEPS}")
    if cfg.device == "cuda" and not torch.cuda.is_available():
        problems.append("device 'cuda' requested but CUDA is not available on this server")
    for name in ("train_file", "eval_file"):
        f = Path(getattr(cfg.data, name))
        if not f.is_file():
            problems.append(f"data.{name} not found on server")
        elif f.stat().st_size <= cfg.model.block_size:
            problems.append(f"data.{name} must be larger than model.block_size ({cfg.model.block_size} bytes)")
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    return cfg


@app.get("/train/configs", dependencies=[Depends(require_training_access)])
def list_train_configs():
    return {"configs": sorted(p.stem for p in Path(CONFIG_DIR).glob("*.json"))}


@app.post("/train", status_code=202, dependencies=[Depends(require_training_access)])
def start_training(r: TrainRequest, response: Response):
    cfg = build_config(r)
    try:
        job = get_jobs().submit(cfg, promote=r.promote)
    except JobConflict as e:
        raise HTTPException(status_code=409, detail={"message": str(e), "active_job": e.active_id})
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
