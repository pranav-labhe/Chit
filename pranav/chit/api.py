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
    CHIT_ALLOW_UNAUTHENTICATED_TRAINING
                          "1" enables training/knowledge without CHIT_API_KEY (local dev only)

Run with a single worker (the default). Model state and the training job
registry live in this process, so --workers N would give each worker its own
model and allow N concurrent training runs.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import secrets
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, Union

import torch
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .bridge import Bridge, Context
from .config import ChitConfig, ConfigError, ModelConfig, load_config
from .jobs import JobConflict, JobFinished, JobNotFound, TrainingJobManager
from .knowledge import KnowledgeError, KnowledgeStore, build_dataset
from .memory import MemoryStore
from .runtime import ChitRuntime
from .tokenizer import ByteTokenizer
from .training import ARCHITECTURE_KEYS

log = logging.getLogger(__name__)

CHECKPOINT = os.environ.get("CHIT_CHECKPOINT", "checkpoints/latest.pt")
API_KEY = os.environ.get("CHIT_API_KEY")
CONFIG_DIR = os.environ.get("CHIT_CONFIG_DIR", "configs")
JOBS_DIR = os.environ.get("CHIT_JOBS_DIR", "checkpoints/jobs")
MAX_TRAIN_STEPS = int(os.environ.get("CHIT_MAX_TRAIN_STEPS", "100000"))
MEMORY_PATH = os.environ.get("CHIT_MEMORY_PATH", "data/memory.json")
KNOWLEDGE_DB = os.environ.get("CHIT_KNOWLEDGE_DB", "data/knowledge.db")
MAX_DATASET_BYTES = int(float(os.environ.get("CHIT_MAX_DATASET_MB", "200")) * 1024 * 1024)
ALLOW_UNAUTHENTICATED_TRAINING = os.environ.get("CHIT_ALLOW_UNAUTHENTICATED_TRAINING") == "1"
MAX_KNOWLEDGE_BATCH = 500

_state: dict = {"runtime": None, "bridge": None, "error": None, "jobs": None, "memory": None, "knowledge": None}
_lock = threading.Lock()  # one generation at a time; the model is not built for parallel calls


def _load_served_model() -> None:
    if not Path(CHECKPOINT).exists():
        _state.update(runtime=None, bridge=None, error=f"checkpoint not found: {CHECKPOINT} (train first)")
        return
    try:
        rt = ChitRuntime.from_checkpoint(CHECKPOINT, memory=_state["memory"])
        _state.update(runtime=rt, bridge=Bridge(rt), error=None)
    except Exception as e:  # bad/incompatible checkpoint: stay up, report via /health
        log.exception("could not load %s", CHECKPOINT)
        _state.update(runtime=None, bridge=None, error=f"{type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state.update(runtime=None, bridge=None, error=None, jobs=None,
                  memory=MemoryStore(MEMORY_PATH), knowledge=KnowledgeStore(KNOWLEDGE_DB))
    _load_served_model()
    _state["jobs"] = TrainingJobManager(JOBS_DIR, on_success=promote_checkpoint)
    try:
        yield
    finally:
        _state["jobs"].shutdown()


app = FastAPI(title="Chit API", version=__version__, lifespan=lifespan)


# --------------------------------------------------------------------------- auth & deps
ALLOW_UNAUTHENTICATED_TRAINING=1

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


def get_memory() -> MemoryStore:
    if _state["memory"] is None:
        raise HTTPException(status_code=503, detail="memory not initialised")
    return _state["memory"]


def get_knowledge() -> KnowledgeStore:
    if _state["knowledge"] is None:
        raise HTTPException(status_code=503, detail="knowledge store not initialised")
    return _state["knowledge"]


def get_jobs() -> TrainingJobManager:
    if _state["jobs"] is None:
        raise HTTPException(status_code=503, detail="training service not started")
    return _state["jobs"]


# --------------------------------------------------------------------------- inference & memory


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=2000)
    tokens: int = Field(default=100, ge=1, le=500)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="0 = greedy")
    top_k: int = Field(default=50, ge=1, le=256)
    stop: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(default_factory=list, max_length=8)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    task: str = Field(default="chat", max_length=50)


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
            "training_job": jobs.active_id() if jobs else None}


@app.get("/model", dependencies=[Depends(require_key)])
def model_info():
    rt = get_runtime()
    return {"model_config": rt.model_config, "parameters": rt.model.num_parameters(),
            "device": str(rt.device), "checkpoint": rt.checkpoint_meta}


@app.post("/generate", dependencies=[Depends(require_key)])
def generate(r: GenerateRequest):
    rt = get_runtime()
    with _lock:
        text = rt.generate(r.prompt, r.tokens, r.temperature, r.top_k, stop=r.stop)
    return {"text": text}


@app.post("/chat", dependencies=[Depends(require_key)])
def chat(r: ChatRequest):
    get_runtime()
    with _lock:
        d = _state["bridge"].process(Context(user_input=r.message, task=r.task))
    return {"text": d.text, "metadata": d.metadata}


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


def promote_checkpoint(job_checkpoint: Path) -> None:
    """Make a finished job's checkpoint the served model.

    The checkpoint is loaded first, so a file that cannot be served is never
    promoted. It is then copied over CHECKPOINT atomically and swapped in under
    the generation lock, so no request ever sees a half-loaded model.
    """
    rt = ChitRuntime.from_checkpoint(job_checkpoint, memory=_state["memory"])
    target = Path(CHECKPOINT)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    try:
        shutil.copyfile(job_checkpoint, tmp)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
    rt.checkpoint_meta["path"] = str(target)
    with _lock:
        _state.update(runtime=rt, bridge=Bridge(rt), error=None)
    log.info("promoted %s -> %s and reloaded the model", job_checkpoint, target)


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
    warmup_steps: int | None = Field(default=None, ge=0)
    lr_schedule: Literal["constant", "cosine"] | None = None
    min_lr_ratio: float | None = Field(default=None, ge=0.0, le=1.0)


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
    promote: bool = Field(default=True, description="serve the new model when training succeeds")


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
    changed = [k for k in ARCHITECTURE_KEYS if getattr(model, k) != served.get(k)]
    if changed:
        if r.init == "current":
            raise HTTPException(status_code=422, detail=[
                f"init 'current' cannot change the architecture ({', '.join(changed)}); use init 'scratch'"])
        return cfg, None
    return dataclasses.replace(cfg, model=model), Path(CHECKPOINT)


def validate_config(cfg: ChitConfig) -> None:
    problems = []
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


def _snapshot_init(init: Path | None, job_dir: Path) -> Path | None:
    """Copy the starting checkpoint into the job, so the run is reproducible later."""
    if init is None:
        return None
    job_dir.mkdir(parents=True, exist_ok=True)
    dst = job_dir / "init.pt"
    shutil.copyfile(init, dst)
    return dst


def _submit(cfg: ChitConfig, r: TrainRequest, job_id: str, init: Path | None, **kw) -> dict:
    try:
        return get_jobs().submit(cfg, promote=r.promote, job_id=job_id, init_checkpoint=init, **kw)
    except JobConflict as e:
        raise HTTPException(status_code=409, detail={"message": str(e), "active_job": e.active_id})


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
        cfg = dataclasses.replace(cfg, data=dataclasses.replace(cfg.data, train_file=str(ds.train_file)))
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
