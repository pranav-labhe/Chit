"""Bounded, extractive conversation summaries and a deduplicating worker."""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor


def summarize_history(turns: list[dict], previous: str = "", max_chars: int = 1200) -> str:
    """Create a small narrative digest by extracting, never inventing, turn text."""
    events = []
    pending_user = None
    for turn in turns:
        content = re.sub(r"\s+", " ", turn["content"]).strip()
        content = content[:240] + ("…" if len(content) > 240 else "")
        if turn["role"] == "user":
            pending_user = content
        elif pending_user is not None:
            events.append(f"The user said: {pending_user} Chit replied: {content}")
            pending_user = None
        else:
            events.append(f"Chit replied: {content}")
    if pending_user is not None:
        events.append(f"The user said: {pending_user}")
    pieces = ([previous.strip()] if previous.strip() else []) + events
    selected = []
    used = len("Earlier conversation: ")
    for piece in reversed(pieces):
        addition = len(piece) + (1 if selected else 0)
        if used + addition <= max_chars:
            selected.append(piece)
            used += addition
    return "Earlier conversation: " + " ".join(reversed(selected))


class SessionSummaryWorker:
    """Single-thread, deduplicating background summarizer for a SessionStore."""

    def __init__(self, store, max_pending: int = 128):
        self.store = store
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chit-session-summary")
        self._lock = threading.Lock()
        self._pending: set[str] = set()
        self.max_pending = max_pending

    def submit(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._pending:
                return
            if len(self._pending) >= self.max_pending:
                self.store.set_summary_error(session_id, "summary queue is full; retry after load falls")
                return
            self._pending.add(session_id)
        future = self._executor.submit(self.store.summarize_overflow, session_id)
        future.add_done_callback(lambda f: self._finish(session_id, f))

    def _finish(self, session_id: str, future) -> None:
        succeeded = True
        try:
            future.result()
        except Exception as exc:
            succeeded = False
            self.store.set_summary_error(session_id, f"{type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._pending.discard(session_id)
            if succeeded:
                try:
                    if self.store.summary_needed(session_id):
                        self.submit(session_id)
                except Exception:
                    pass  # the session may have been deleted while work was queued

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
