import asyncio
import threading

import pytest

from pranav.chit.inference import InferenceManager, InferenceOverloaded


def test_bounded_fifo_rejects_overload_and_runs_off_event_loop():
    async def scenario():
        manager = InferenceManager(max_queue_size=1, queue_timeout_seconds=5)
        await manager.start()
        entered = threading.Event()
        release = threading.Event()

        def slow():
            entered.set()
            release.wait(3)
            return "first"

        first = asyncio.create_task(manager.run(slow))
        assert await asyncio.to_thread(entered.wait, 2)
        second = asyncio.create_task(manager.run(lambda: "second"))
        await asyncio.sleep(0)
        with pytest.raises(InferenceOverloaded, match="queue is full"):
            await manager.run(lambda: "third")
        release.set()
        assert await first == "first"
        assert await second == "second"
        assert manager.stats["completed"] == 2
        await manager.close()

    asyncio.run(scenario())


def test_cancelled_queued_request_is_skipped():
    async def scenario():
        manager = InferenceManager(max_queue_size=2, queue_timeout_seconds=5)
        await manager.start()
        entered = threading.Event()
        release = threading.Event()
        ran = []

        def slow():
            entered.set()
            release.wait(3)
            return 1

        first = asyncio.create_task(manager.run(slow))
        assert await asyncio.to_thread(entered.wait, 2)
        queued = asyncio.create_task(manager.run(lambda: ran.append("cancelled")))
        await asyncio.sleep(0)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        release.set()
        assert await first == 1
        await asyncio.sleep(0.02)
        assert ran == []
        await manager.close()

    asyncio.run(scenario())
