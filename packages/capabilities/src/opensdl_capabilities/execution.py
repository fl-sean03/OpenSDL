"""Where adapter code runs, and what a declared timeout can therefore promise.

`asyncio.wait_for` can interrupt a coroutine only at an await point. An adapter that wraps a
blocking vendor SDK — a synchronous call inside an `async def`, which is the shape nearly every
vendor SDK forces — never reaches one. Measured on the shipped reference runtime: a declared
timeout of 0.1 seconds against an adapter that computed for 2.0 seconds elapsed 2.01 seconds and
raised nothing, and a concurrent run that costs 0.05 seconds finished 1.02 seconds after
submission because the blocking call held the only event loop in the process. So the declared
timeout was advisory, `max_concurrency` was a fiction, and one adapter could stall every other
run's timeout, lease handling and event writing.

Adapter code therefore runs on a worker thread with its own event loop — one loop per adapter —
and the runtime waits on a handle it can abandon. That bounds how long the runtime waits, and it
keeps the loop that runs the laboratory free.

It does not stop the work, and no timeout in any design could. Nothing in software un-aspirates a
pipette or un-heats a reactor; `SAFETY.md` is explicit that a database rollback does not reverse a
physical action, and the same holds here. An abandoned call keeps running on its thread until it
returns. Cancellation is *requested* — an adapter that never awaits cannot receive it — and the
thread is a daemon, so the process will not wait for abandoned work at exit. What a timeout
records is that the runtime stopped waiting, not that anything stopped.

One adapter, one loop: `start`, `execute`, `health` and `close` all run on that adapter's own loop,
so an adapter may hold `asyncio` primitives across its own lifecycle. It must not share them with
the loop that called the runtime, because that loop is a different loop.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from typing import Any, TypeVar

from opensdl_core import ExecutionRequest, ExecutionResult

from .adapter import CapabilityAdapter

T = TypeVar("T")

#: A coroutine is built inside the worker thread rather than passed in, so nothing about the call
#: is constructed on the caller's loop.
CoroutineFactory = Callable[[], Coroutine[Any, Any, T]]


class AdapterCall:
    """One dispatched adapter execution the runtime can stop waiting for."""

    def __init__(
        self,
        adapter_name: str,
        waiter: "asyncio.Future[ExecutionResult]",
        request_cancellation: Callable[[], None],
    ) -> None:
        self.adapter_name = adapter_name
        self._waiter = waiter
        self._request_cancellation = request_cancellation

    async def result(self, timeout: float | None = None) -> ExecutionResult:
        """Wait up to `timeout` seconds for the adapter, then stop waiting.

        Timing out or being cancelled asks the adapter to stop and gives up on the answer. It does
        not establish that the adapter stopped: a blocking call has no point at which to receive
        the request, and even an adapter that receives it may already have moved the equipment.
        """
        try:
            return await asyncio.wait_for(self._waiter, timeout)
        except BaseException:
            self.request_cancellation()
            raise

    def request_cancellation(self) -> None:
        self._request_cancellation()


class AdapterExecutor:
    """Runs every interaction with an adapter on that adapter's own event loop."""

    def __init__(self) -> None:
        self._workers: dict[str, _AdapterWorker] = {}
        self._guard = threading.Lock()

    def dispatch(self, adapter: CapabilityAdapter, request: ExecutionRequest) -> AdapterCall:
        """Hand one execution to the adapter's loop and return a handle to it."""
        settled, cancel = self._worker(adapter).submit(lambda: adapter.execute(request))
        return AdapterCall(adapter.name, _bridge(settled), cancel)

    async def start(self, adapter: CapabilityAdapter) -> None:
        await self._run(adapter, adapter.start)

    async def close(self, adapter: CapabilityAdapter) -> None:
        await self._run(adapter, adapter.close)

    async def health(self, adapter: CapabilityAdapter) -> dict[str, Any]:
        return await self._run(adapter, adapter.health)

    def shutdown(self) -> None:
        """Stop every adapter loop. Work already abandoned is not waited for."""
        with self._guard:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.stop()

    async def _run(self, adapter: CapabilityAdapter, method: CoroutineFactory[T]) -> T:
        settled, _ = self._worker(adapter).submit(method)
        return await _bridge(settled)

    def _worker(self, adapter: CapabilityAdapter) -> "_AdapterWorker":
        with self._guard:
            worker = self._workers.get(adapter.name)
            if worker is None:
                worker = _AdapterWorker(f"opensdl-adapter-{adapter.name}")
                self._workers[adapter.name] = worker
            return worker


class _AdapterWorker:
    """A daemon thread running one adapter's event loop for the life of the process.

    The thread is a daemon because the alternative is a process that cannot exit while an
    abandoned instrument call is still running. Abandoning the wait is the honest outcome; waiting
    for it at interpreter exit would hide the cost of an adapter that never returns.
    """

    def __init__(self, name: str) -> None:
        self._started = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._serve, name=name, daemon=True)
        self._thread.start()
        self._started.wait()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        loop = self._loop
        if loop is None:  # pragma: no cover - the constructor waits for the loop
            raise RuntimeError("adapter worker loop was never started")
        return loop

    def submit(self, factory: CoroutineFactory[T]) -> tuple["Future[T]", Callable[[], None]]:
        settled: Future[T] = Future()
        running: list[asyncio.Task[T]] = []

        def _finish(task: asyncio.Task[T]) -> None:
            if settled.done():  # pragma: no cover - only a second completion reaches this
                return
            if task.cancelled():
                settled.set_exception(asyncio.CancelledError())
                return
            error = task.exception()
            if error is not None:
                settled.set_exception(error)
            else:
                settled.set_result(task.result())

        def _start() -> None:
            # The caller gave up before the loop reached this, so the adapter is never called and
            # no physical action happens. Starting it now would dispatch work nobody awaits.
            if not settled.set_running_or_notify_cancel():  # pragma: no cover - narrow race
                return
            task = self.loop.create_task(factory())
            running.append(task)
            task.add_done_callback(_finish)

        def _cancel() -> None:
            def _apply() -> None:
                for task in running:
                    task.cancel()

            try:
                self.loop.call_soon_threadsafe(_apply)
            except RuntimeError:  # pragma: no cover - the adapter loop is already gone
                pass

        self.loop.call_soon_threadsafe(_start)
        return settled, _cancel

    def stop(self) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():  # pragma: no cover - stop is idempotent
            return
        try:
            loop.call_soon_threadsafe(loop.stop)
        except RuntimeError:  # pragma: no cover - the loop closed between the two statements
            pass

    def _serve(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._started.set()
        try:
            loop.run_forever()
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def _bridge(settled: "Future[T]") -> "asyncio.Future[T]":
    """Mirror a worker-thread result onto the calling loop, tolerating a caller that gave up.

    A caller that timed out has already cancelled the future returned here, and the loop it was
    created on may be closed by the time the adapter finally returns. Both are expected on the
    abandonment path, so neither is allowed to raise inside the worker thread.
    """
    loop = asyncio.get_running_loop()
    waiter: asyncio.Future[T] = loop.create_future()

    def _relay(source: "Future[T]") -> None:
        def _apply() -> None:
            if waiter.done():
                return
            if source.cancelled():  # pragma: no cover - only a pre-start cancel reaches this
                waiter.cancel()
                return
            error = source.exception()
            if error is not None:
                waiter.set_exception(error)
            else:
                waiter.set_result(source.result())

        try:
            loop.call_soon_threadsafe(_apply)
        except RuntimeError:  # pragma: no cover - nothing is waiting on a closed loop
            pass

    settled.add_done_callback(_relay)
    return waiter
