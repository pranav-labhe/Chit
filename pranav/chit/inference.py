"""Bounded, single-device inference admission and execution.

The scheduler owns admission on the ASGI event loop and runs model calls on a
dedicated worker thread. This keeps synchronous PyTorch work off the event loop
and prevents concurrent calls into one model/device. Micro-batching is a later
optimization; this first implementation deliberately executes FIFO.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class InferenceOverloaded(RuntimeError):
    """The bounded inference queue is full or the queue deadline expired."""


@dataclass
class _WorkItem(Generic[T]):
    fn: Callable[[], T]
    result: asyncio.Future[T]
    started_event: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled: bool = False
    started: bool = False


class InferenceManager:
    def __init__(self, max_queue_size: int = 32, queue_timeout_seconds: float = 30.0):
        if max_queue_size < 1 or queue_timeout_seconds <= 0:
            raise ValueError("inference queue size and timeout must be positive")
        self._queue: asyncio.Queue[_WorkItem] = asyncio.Queue(maxsize=max_queue_size)
        self.queue_timeout_seconds = float(queue_timeout_seconds)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chit-inference")
        self._worker: asyncio.Task | None = None
        self._accepting = False
        self._active = 0
        self._completed = 0
        self._rejected = 0

    @property
    def stats(self) -> dict:
        return {"queue_depth": self._queue.qsize(), "queue_capacity": self._queue.maxsize,
                "active": self._active, "completed": self._completed,
                "rejected": self._rejected, "accepting": self._accepting}

    async def start(self) -> None:
        if self._worker is not None:
            return
        self._accepting = True
        self._worker = asyncio.create_task(self._run(), name="chit-inference-queue")

    async def close(self, drain_timeout: float = 30.0) -> None:
        self._accepting = False
        if self._worker is None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            return
        try:
            await asyncio.wait_for(self._queue.join(), timeout=max(0.0, drain_timeout))
        except asyncio.TimeoutError:
            pass
        self._worker.cancel()
        try:
            await self._worker
        except asyncio.CancelledError:
            pass
        while not self._queue.empty():
            item = self._queue.get_nowait()
            item.started_event.set()
            if not item.result.done():
                item.result.set_exception(InferenceOverloaded("service is shutting down"))
            self._queue.task_done()
        self._worker = None
        # Do not wait indefinitely for a backend call during shutdown.
        self._executor.shutdown(wait=False, cancel_futures=True)

    async def run(self, fn: Callable[[], T]) -> T:
        if not self._accepting or self._worker is None:
            raise InferenceOverloaded("inference service is not accepting requests")
        loop = asyncio.get_running_loop()
        item: _WorkItem[T] = _WorkItem(fn, loop.create_future())
        item.result.add_done_callback(lambda future: future.exception()
                                      if not future.cancelled() else None)
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull as exc:
            self._rejected += 1
            raise InferenceOverloaded("inference queue is full") from exc
        try:
            # The timeout bounds queue wait only. Once execution starts, callers
            # wait for the backend result; interrupting an active device batch is
            # unsafe and the underlying executor call cannot be force-stopped.
            await asyncio.wait_for(asyncio.shield(item.started_event.wait()), self.queue_timeout_seconds)
            return await asyncio.shield(item.result)
        except asyncio.TimeoutError as exc:
            if item.started:
                return await asyncio.shield(item.result)
            item.cancelled = True
            self._rejected += 1
            raise InferenceOverloaded("inference queue deadline exceeded") from exc
        except asyncio.CancelledError:
            if not item.started:
                item.cancelled = True
            raise

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            item = await self._queue.get()
            try:
                if item.cancelled or item.result.cancelled():
                    if not item.result.done():
                        item.result.cancel()
                    continue
                item.started = True
                item.started_event.set()
                self._active = 1
                try:
                    value = await loop.run_in_executor(self._executor, item.fn)
                except asyncio.CancelledError:
                    if not item.result.done():
                        item.result.set_exception(InferenceOverloaded("service shut down during inference"))
                    raise
                except Exception as exc:
                    if not item.result.done():
                        item.result.set_exception(exc)
                else:
                    if not item.result.done():
                        item.result.set_result(value)
                    self._completed += 1
                finally:
                    self._active = 0
            finally:
                self._queue.task_done()
