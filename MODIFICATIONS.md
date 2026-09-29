# Existing-file changes

Apply these changes to the existing branch files. The three new Python modules and three new tests are already included in this bundle.

## `pranav/chit/formats.py`

Change:

```python
def render_chat_prompt(user_input: str, memories: list[str], task: str = "chat") -> str:
    mem = "\n".join(f"- {m}" for m in memories if m) or "- (none)"
    return f"Task: {task}\nKnown memory:\n{mem}\n{USER} {user_input.strip()}\n{ASSISTANT}"
```

to:

```python
def render_chat_prompt(
    user_input: str,
    memories: list[str],
    task: str = "chat",
    turns: list[dict] | None = None,
) -> str:
    history_lines = []
    for turn in turns or []:
        label = USER if turn.get("role") == "user" else ASSISTANT
        content = str(turn.get("content", "")).strip()
        if content:
            history_lines.append(f"{label} {content}")
    history = "\n".join(history_lines) or "- (none)"
    mem = "\n".join(f"- {m}" for m in memories if m) or "- (none)"
    return (
        f"Task: {task}\n"
        f"Conversation history:\n{history}\n"
        f"Known memory:\n{mem}\n"
        f"{USER} {user_input.strip()}\n{ASSISTANT}"
    )
```

## `pranav/chit/bridge.py`

Add `session_turns` to `Context`:

```python
session_turns: list[dict] = field(default_factory=list)
```

Extend the constructor with `max_turns: int = 16` and store it:

```python
self.max_turns = max_turns
```

Change `process()` to include the bounded session history:

```python
def process(self, c: Context) -> ChitDecision:
    memories = (c.memories or self.runtime.recall(c.user_input, self.max_memories))[: self.max_memories]
    turns = (c.session_turns or [])[-self.max_turns:]
    prompt = render_chat_prompt(
        c.user_input,
        [m.get("content", "") for m in memories],
        task=c.task,
        turns=turns,
    )
    text = self.runtime.generate(prompt, self.max_new_tokens, self.temperature, stop=self.STOP).strip()
    return ChitDecision(
        text,
        metadata={
            "task": c.task,
            "memory_ids": [m.get("id") for m in memories],
            "session_turn_count": len(turns),
        },
    )
```

## `pranav/chit/jobs.py`

Add:

```python
class JobNotReady(Exception):
    """A candidate is not in a state where it can be promoted."""
```

In `TrainingJobManager.__init__`, add:

```python
self._promotion_lock = threading.Lock()
```

Add `candidate_checkpoint` to `TrainingJob.snapshot()`:

```python
'candidate_checkpoint': self.checkpoint if self.state == JobState.SUCCEEDED and not self.promoted else None,
```

Add this method to `TrainingJobManager`:

```python
def promote(self, job_id: str) -> dict:
    """Promote a successful candidate checkpoint through the configured callback."""
    with self._promotion_lock:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            if job.state != JobState.SUCCEEDED:
                raise JobNotReady(f"job {job_id} is {job.state.value}; only succeeded jobs can be promoted")
            if job.promoted:
                return job.snapshot()
            if not job.checkpoint:
                raise JobNotReady(f"job {job_id} has no candidate checkpoint")
            callback = self.on_success
            checkpoint = Path(job.checkpoint)

        if callback is None:
            raise RuntimeError("no checkpoint promotion callback is configured")
        try:
            callback(checkpoint)
        except Exception as e:
            self._update(job, persist=True, promotion_error=f'{type(e).__name__}: {e}')
            raise

        self._update(job, persist=True, promoted=True, promotion_error=None)
        return self.get(job_id)
```

## `pranav/chit/api.py`

Imports:

```python
from .jobs import JobConflict, JobFinished, JobNotFound, JobNotReady, TrainingJobManager
from .session import SessionStore
```

State/env:

```python
SESSION_DB = os.environ.get("CHIT_SESSION_DB", "data/sessions.db")

_state: dict = {"runtime": None, "bridge": None, "error": None, "jobs": None,
                "memory": None, "knowledge": None, "sessions": None}
```

In `lifespan()` initialize:

```python
_state.update(runtime=None, bridge=None, error=None, jobs=None,
              memory=MemoryStore(MEMORY_PATH),
              knowledge=KnowledgeStore(KNOWLEDGE_DB),
              sessions=SessionStore(SESSION_DB))
```

Add:

```python
def get_sessions() -> SessionStore:
    if _state["sessions"] is None:
        raise HTTPException(status_code=503, detail="session store not initialised")
    return _state["sessions"]
```

Extend `ChatRequest`:

```python
session_id: str | None = Field(default=None, min_length=1, max_length=128,
                               pattern=r"^[A-Za-z0-9_-]+$")
```

Replace `/chat` with:

```python
@app.post("/chat", dependencies=[Depends(require_key)])
def chat(r: ChatRequest):
    get_runtime()
    sessions = get_sessions()
    if r.session_id:
        session = sessions.get(r.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
    else:
        session = sessions.create()

    turns = session["turns"]
    with _lock:
        d = _state["bridge"].process(Context(
            user_input=r.message,
            task=r.task,
            session_turns=turns,
        ))
        sessions.append_exchange(session["id"], r.message, d.text)
    return {
        "text": d.text,
        "session_id": session["id"],
        "metadata": {**d.metadata, "session_id": session["id"], "session_turn_count": len(turns)},
    }
```

Add session endpoints near inference/memory endpoints:

```python
@app.post("/sessions", status_code=201, dependencies=[Depends(require_key)])
def create_session():
    return get_sessions().create()


@app.get("/sessions/{session_id}", dependencies=[Depends(require_key)])
def get_session(session_id: str):
    session = get_sessions().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@app.delete("/sessions/{session_id}", status_code=204, dependencies=[Depends(require_key)])
def delete_session(session_id: str):
    if not get_sessions().delete(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)
```

Add explicit candidate promotion after the existing cancel endpoint:

```python
@app.post("/train/{job_id}/promote", dependencies=[Depends(require_training_access)])
def promote_training_job(job_id: str):
    try:
        before = get_jobs().get(job_id)
        if before["state"] != "succeeded":
            raise HTTPException(
                status_code=409,
                detail=f"job {job_id} is {before['state']}; only succeeded candidates can be promoted",
            )
        job = get_jobs().promote(job_id)
    except JobNotFound:
        raise HTTPException(status_code=404, detail="training job not found")
    except JobNotReady as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"candidate promotion failed: {type(e).__name__}: {e}")

    knowledge = job.get("metadata", {}).get("knowledge", {})
    ids = knowledge.get("entry_ids", [])
    if ids:
        get_knowledge().mark_trained(ids, job_id)
    return get_jobs().get(job_id)
```

In `train_on_knowledge()`, extend the `knowledge` metadata object with:

```python
"entry_ids": ids,
```

This is important because a knowledge candidate can be promoted later, even after a process restart, and the knowledge entries must only become `trained` at that point.

## `tests/conftest.py`

Add to the fixture:

```python
monkeypatch.setattr(api, "SESSION_DB", str(tmp_path / "data" / "sessions.db"))
```

## `requirements.txt`

Apply `requirements.txt.patch` in this bundle. PyPI currently lists `pypdf 6.19.0` as the latest release (Sep 16, 2026), so the proposed constraint is `>=6.19,<7`. citeturn766116search0
