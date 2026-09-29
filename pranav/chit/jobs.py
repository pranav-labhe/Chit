"""Background training jobs for the Chit API.

One job runs at a time: a single CPU/GPU cannot usefully train two models at
once, and a second run would compete with the model that is serving requests.
Each job trains into its own directory (``<jobs_dir>/<job_id>/``), so a failed
or cancelled run can never overwrite the checkpoint that is being served.
Only a successful run is handed to ``on_success``, which the API uses to
promote the checkpoint and hot-reload the model.

Job records are kept in memory (the most recent ``max_jobs``) and written to
``<job dir>/job.json`` at every state change, as an audit trail that survives
restarts. A job that was running when the process stopped is not resumed.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from .config import ChitConfig
from .training import TrainingCancelled, train

log = logging.getLogger(__name__)

MAX_HISTORY_POINTS = 1000  # evaluation points kept per job


class JobState(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

    @property
    def terminal(self) -> bool:
        return self in (JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED)


class JobConflict(Exception):
    """Another job is already queued or running."""

    def __init__(self, active_id: str):
        super().__init__(f'training job {active_id} is already active')
        self.active_id = active_id


class JobNotFound(KeyError):
    pass


class JobFinished(Exception):
    """The job already reached a terminal state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TrainingJob:
    id: str
    config: dict
    output_dir: str
    promote: bool
    max_steps: int
    state: JobState = JobState.QUEUED
    step: int = 0
    history: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    checkpoint: str | None = None
    promoted: bool = False
    promotion_error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def snapshot(self) -> dict:
        return {
            'id': self.id,
            'state': self.state.value,
            'step': self.step,
            'max_steps': self.max_steps,
            'progress': round(self.step / self.max_steps, 4) if self.max_steps else 0.0,
            'latest': self.history[-1] if self.history else None,
            'history': list(self.history),
            'config': self.config,
            'promote': self.promote,
            'promoted': self.promoted,
            'promotion_error': self.promotion_error,
            'checkpoint': self.checkpoint,
            'error': self.error,
            'cancel_requested': self.cancel_event.is_set(),
            'created_at': self.created_at,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
        }


class TrainingJobManager:
    def __init__(
        self,
        jobs_dir: str | os.PathLike,
        on_success: Callable[[Path], None] | None = None,
        max_jobs: int = 50,
    ):
        self.jobs_dir = Path(jobs_dir)
        self.on_success = on_success
        self.max_jobs = max_jobs
        self._jobs: OrderedDict[str, TrainingJob] = OrderedDict()
        self._lock = threading.Lock()
        self._active: tuple[TrainingJob, threading.Thread] | None = None

    # ---------- public API (thread-safe; returns snapshots, never live objects)

    def submit(self, cfg: ChitConfig, promote: bool = True) -> dict:
        with self._lock:
            if self._active and not self._active[0].state.terminal:
                raise JobConflict(self._active[0].id)
            job_id = uuid.uuid4().hex
            out = self.jobs_dir / job_id
            job = TrainingJob(id=job_id, config=asdict(cfg), output_dir=str(out),
                              promote=promote, max_steps=cfg.training.max_steps)
            self._jobs[job_id] = job
            while len(self._jobs) > self.max_jobs:
                oldest = next(iter(self._jobs))
                if not self._jobs[oldest].state.terminal:
                    break
                self._jobs.popitem(last=False)
            thread = threading.Thread(target=self._run, args=(job, cfg),
                                      name=f'chit-train-{job_id[:8]}', daemon=True)
            self._active = (job, thread)
            self._persist(job)
            snap = job.snapshot()
        thread.start()
        log.info('training job %s submitted (max_steps=%d, promote=%s)', job_id, job.max_steps, promote)
        return snap

    def get(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            return job.snapshot()

    def list(self) -> list[dict]:
        with self._lock:
            return [j.snapshot() for j in reversed(self._jobs.values())]

    def active_id(self) -> str | None:
        with self._lock:
            if self._active and not self._active[0].state.terminal:
                return self._active[0].id
            return None

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            if job.state.terminal:
                raise JobFinished(f'job {job_id} already {job.state.value}')
            job.cancel_event.set()
            log.info('training job %s: cancellation requested', job_id)
            return job.snapshot()

    def shutdown(self, timeout: float = 30.0) -> None:
        """Cancel the active job (if any) and wait for its thread to stop."""
        with self._lock:
            active = self._active
        if active and not active[0].state.terminal:
            active[0].cancel_event.set()
            active[1].join(timeout)
            if active[1].is_alive():
                log.warning('training job %s did not stop within %.0fs', active[0].id, timeout)

    # ---------- worker

    def _update(self, job: TrainingJob, persist: bool = False, **changes) -> None:
        with self._lock:
            for k, v in changes.items():
                setattr(job, k, v)
            if persist:
                self._persist(job)

    def _on_eval(self, job: TrainingJob, step: int, train_loss: float, eval_loss: float) -> None:
        point = {'step': step, 'train_loss': round(train_loss, 6), 'eval_loss': round(eval_loss, 6), 'at': _now()}
        with self._lock:
            job.history.append(point)
            if len(job.history) > MAX_HISTORY_POINTS:
                del job.history[0]

    def _run(self, job: TrainingJob, cfg: ChitConfig) -> None:
        self._update(job, persist=True, state=JobState.RUNNING, started_at=_now())
        try:
            ckpt = train(
                cfg,
                output_dir=job.output_dir,
                on_step=lambda s: self._update(job, step=s),
                on_eval=lambda s, tl, el: self._on_eval(job, s, tl, el),
                should_stop=job.cancel_event.is_set,
                keep_step_checkpoints=False,
                progress=False,
            )
        except TrainingCancelled as e:
            log.info('training job %s: %s', job.id, e)
            self._finish(job, JobState.CANCELLED)
            return
        except Exception as e:  # report to the client; full traceback stays in the server log
            log.exception('training job %s failed', job.id)
            self._finish(job, JobState.FAILED, error=f'{type(e).__name__}: {e}')
            return

        self._update(job, checkpoint=str(ckpt))
        if job.promote and self.on_success:
            try:
                self.on_success(ckpt)
                self._update(job, promoted=True)
            except Exception as e:  # training succeeded; only the hand-off failed
                log.exception('training job %s: promotion failed', job.id)
                self._update(job, promotion_error=f'{type(e).__name__}: {e}')
        self._finish(job, JobState.SUCCEEDED)
        log.info('training job %s succeeded (promoted=%s)', job.id, job.promoted)

    def _finish(self, job: TrainingJob, state: JobState, error: str | None = None) -> None:
        self._update(job, persist=True, state=state, error=error, finished_at=_now())

    def _persist(self, job: TrainingJob) -> None:
        """Write job.json atomically. Called with self._lock held."""
        try:
            out = Path(job.output_dir)
            out.mkdir(parents=True, exist_ok=True)
            tmp = out / 'job.json.tmp'
            tmp.write_text(json.dumps(job.snapshot(), indent=2), encoding='utf-8')
            os.replace(tmp, out / 'job.json')
        except OSError:  # the audit file is best-effort; never fail the job over it
            log.exception('training job %s: could not write job.json', job.id)
