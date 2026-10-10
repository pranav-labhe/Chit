"""Background training jobs for the Chit API.

One job runs at a time: a single CPU/GPU cannot usefully train two models at
once, and a second run would compete with the model that is serving requests.
Each job trains into its own directory (``<jobs_dir>/<job_id>/``), so a failed
or cancelled run can never overwrite the checkpoint that is being served.
Every saved checkpoint is automatically scored on the held-out text set. A
successful run remains a candidate; promotion is a separate reviewed operation.

Job records are kept in memory (the most recent ``max_jobs``) and written to
``<job dir>/job.json`` at every state change, as an audit trail that survives
restarts. On start-up the manager reloads that history; a job that was still
queued or running when the process stopped is recorded as ``failed``
(interrupted) and is not resumed.
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
GOLDEN_SET_PATH = Path(os.environ.get("CHIT_GOLDEN_SET",
                                     Path(__file__).resolve().parents[2] / "data" / "golden_set.json"))

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
    evaluations: list[dict] = field(default_factory=list)
    evaluation_error: str | None = None
    final_evaluation: str | None = None
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    checkpoint: str | None = None
    promoted: bool = False
    promotion_error: str | None = None
    init_checkpoint: str | None = None
    metadata: dict = field(default_factory=dict)
    post_success_error: str | None = None
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
            'evaluations': list(self.evaluations),
            'evaluation_error': self.evaluation_error,
            'final_evaluation': self.final_evaluation,
            'config': self.config,
            'promote': self.promote,
            'promoted': self.promoted,
            'promotion_error': self.promotion_error,
            'checkpoint': self.checkpoint,
            'init_checkpoint': self.init_checkpoint,
            'metadata': self.metadata,
            'post_success_error': self.post_success_error,
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
        max_jobs: int = 50,
    ):
        self.jobs_dir = Path(jobs_dir)
        self.max_jobs = max_jobs
        self._jobs: OrderedDict[str, TrainingJob] = OrderedDict()
        self._lock = threading.Lock()
        self._active: tuple[TrainingJob, threading.Thread] | None = None
        self._load_history()

    # ---------- public API (thread-safe; returns snapshots, never live objects)

    def submit(
        self,
        cfg: ChitConfig,
        promote: bool = False,
        *,
        job_id: str | None = None,
        init_checkpoint: str | os.PathLike | None = None,
        metadata: dict | None = None,
        after_success: Callable[[dict], None] | None = None,
    ) -> dict:
        """Start training; a success hook may install an explicitly forced candidate."""
        with self._lock:
            if self._active and not self._active[0].state.terminal:
                raise JobConflict(self._active[0].id)
            job_id = job_id or uuid.uuid4().hex
            if job_id in self._jobs:
                raise ValueError(f'job id {job_id} already exists')
            out = self.jobs_dir / job_id
            job = TrainingJob(id=job_id, config=asdict(cfg), output_dir=str(out),
                              promote=promote, max_steps=cfg.training.max_steps,
                              init_checkpoint=str(init_checkpoint) if init_checkpoint else None,
                              metadata=dict(metadata or {}))
            self._jobs[job_id] = job
            while len(self._jobs) > self.max_jobs:
                oldest = next(iter(self._jobs))
                if not self._jobs[oldest].state.terminal:
                    break
                self._jobs.popitem(last=False)
            thread = threading.Thread(target=self._run, args=(job, cfg, after_success),
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

    def _on_checkpoint(self, job: TrainingJob, cfg: ChitConfig, step: int, checkpoint: Path) -> None:
        """Score held-out language metrics for every atomic training checkpoint."""
        try:
            from .tools.eval_runner import evaluate_checkpoint
            report = evaluate_checkpoint(checkpoint, Path(cfg.data.eval_file),
                                         GOLDEN_SET_PATH, include_golden=False)
            output = checkpoint.parent / f"evaluation_step_{step:06d}.json"
            tmp = output.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
            os.replace(tmp, output)
            with self._lock:
                job.evaluations.append({"step": step, "path": str(output),
                                        "bits_per_byte": report["language_model_metrics"]["bits_per_byte"],
                                        "perplexity": report["language_model_metrics"]["perplexity"]})
                self._persist(job)
        except Exception as exc:
            log.exception("training job %s: checkpoint evaluation failed at step %d", job.id, step)
            self._update(job, persist=True,
                         evaluation_error=f"step {step}: {type(exc).__name__}: {exc}")

    def _run(self, job: TrainingJob, cfg: ChitConfig,
             after_success: Callable[[dict], None] | None = None) -> None:
        self._update(job, persist=True, state=JobState.RUNNING, started_at=_now())
        try:
            ckpt = train(
                cfg,
                output_dir=job.output_dir,
                init_checkpoint=job.init_checkpoint,
                metadata={'job_id': job.id, **job.metadata},
                on_step=lambda s: self._update(job, step=s),
                on_eval=lambda s, tl, el: self._on_eval(job, s, tl, el),
                on_checkpoint=lambda s, p: self._on_checkpoint(job, cfg, s, p),
                should_stop=job.cancel_event.is_set,
                keep_step_checkpoints=True,
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
        # Write a final deterministic held-out report. Golden response export
        # remains an explicit eval_runner action because generation is slower
        # than scoring every saved checkpoint and still needs human review.
        try:
            from .tools.eval_runner import evaluate_checkpoint
            report = evaluate_checkpoint(ckpt, Path(cfg.data.eval_file), GOLDEN_SET_PATH,
                                         include_golden=False)
            output = ckpt.parent / "evaluation.json"
            tmp = output.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
            os.replace(tmp, output)
            self._update(job, persist=True, final_evaluation=str(output))
        except Exception as exc:
            log.exception("training job %s: final behavioral evaluation failed", job.id)
            self._update(job, persist=True,
                         evaluation_error=f"final: {type(exc).__name__}: {exc}")
        if after_success:
            try:
                with self._lock:
                    snap = job.snapshot()
                after_success(snap)
                if snap.get('promoted'):
                    self._update(job, persist=True, promoted=True)
            except Exception as e:  # e.g. bookkeeping; the checkpoint itself is fine
                log.exception('training job %s: post-success hook failed', job.id)
                if snap.get('promoted'):
                    self._update(job, persist=True, promoted=True,
                                 post_success_error=f'{type(e).__name__}: {e}')
                elif job.promote:
                    self._update(job, persist=True, promotion_error=f'{type(e).__name__}: {e}')
                else:
                    self._update(job, post_success_error=f'{type(e).__name__}: {e}')
        self._finish(job, JobState.SUCCEEDED)
        log.info('training job %s succeeded (promoted=%s)', job.id, job.promoted)

    def _finish(self, job: TrainingJob, state: JobState, error: str | None = None) -> None:
        self._update(job, persist=True, state=state, error=error, finished_at=_now())

    def _load_history(self) -> None:
        """Reload job records from ``<jobs_dir>/*/job.json`` (newest ``max_jobs``)."""
        if not self.jobs_dir.is_dir():
            return
        records = []
        for f in self.jobs_dir.glob('*/job.json'):
            try:
                records.append(json.loads(f.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                log.warning('skipping unreadable job record %s', f)
        records.sort(key=lambda r: r.get('created_at') or '')
        for r in records[-self.max_jobs:]:
            try:
                job = TrainingJob(
                    id=r['id'], config=r.get('config') or {}, output_dir=str(self.jobs_dir / r['id']),
                    promote=bool(r.get('promote')), max_steps=int(r.get('max_steps') or 0),
                    state=JobState(r['state']), step=int(r.get('step') or 0),
                    history=list(r.get('history') or []), created_at=r.get('created_at') or _now(),
                    evaluations=list(r.get('evaluations') or []), evaluation_error=r.get('evaluation_error'),
                    final_evaluation=r.get('final_evaluation'),
                    started_at=r.get('started_at'), finished_at=r.get('finished_at'), error=r.get('error'),
                    checkpoint=r.get('checkpoint'), promoted=bool(r.get('promoted')),
                    promotion_error=r.get('promotion_error'), init_checkpoint=r.get('init_checkpoint'),
                    metadata=r.get('metadata') or {}, post_success_error=r.get('post_success_error'))
            except (KeyError, ValueError, TypeError):
                log.warning('skipping malformed job record for %s', r.get('id'))
                continue
            if not job.state.terminal:  # the process died while this job was active
                job.state, job.error = JobState.FAILED, 'interrupted: server stopped before the job finished'
                job.finished_at = job.finished_at or _now()
                self._persist(job)
            self._jobs[job.id] = job

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
