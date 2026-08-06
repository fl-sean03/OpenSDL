"""Contract tests for where adapter code runs.

Adapter execution moved off the calling loop so that a declared timeout binds a blocking adapter
and so that one adapter cannot stall the laboratory. That move has an obligation attached: an
adapter must still be able to hold state across its own lifecycle, which means `start`, `execute`,
`health` and `close` all have to reach it on one loop. These tests pin that obligation, because a
change that routes only `execute` through the executor passes every runtime test and then breaks
any adapter holding a lock, a queue, or a connection.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from opensdl_capabilities import (
    AdapterExecutor,
    CapabilityAdapter,
    CapabilityRegistry,
    NotDispatchedError,
)
from opensdl_core import (
    CapabilityDefinition,
    ExecutionRequest,
    ExecutionResult,
    ExecutorType,
    OpenSDLError,
)


class StatefulAdapter(CapabilityAdapter):
    """Holds an `asyncio.Lock` across its whole lifecycle, as a connected instrument must."""

    name = "stateful"

    def __init__(self) -> None:
        super().__init__()
        self._lock = asyncio.Lock()
        self.loops: list[int] = []
        self.closed = False

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="test.stateful",
                name="Stateful",
                executor_type=ExecutorType.INSTRUMENT,
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        ]

    async def _record(self) -> None:
        async with self._lock:
            self.loops.append(id(asyncio.get_running_loop()))

    async def start(self) -> None:
        await self._record()

    async def health(self) -> dict[str, object]:
        await self._record()
        return {"status": "healthy", "adapter": self.name}

    async def close(self) -> None:
        await self._record()
        self.closed = True

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        await self._record()
        return ExecutionResult(request_id=request.request_id, output={"ok": True})


class BlockingAdapter(CapabilityAdapter):
    """An `async def` with no await in it: the shape a blocking vendor SDK forces."""

    name = "blocking"

    def __init__(self, *, seconds: float) -> None:
        super().__init__()
        self.seconds = seconds
        self.finished = threading.Event()

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="test.blocking",
                name="Blocking",
                executor_type=ExecutorType.COMPUTE,
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        deadline = time.monotonic() + self.seconds
        while time.monotonic() < deadline:
            pass
        self.finished.set()
        return ExecutionResult(request_id=request.request_id, output={"ok": True})


@pytest.mark.asyncio
async def test_an_adapter_reaches_its_whole_lifecycle_on_one_loop() -> None:
    adapter = StatefulAdapter()
    registry = CapabilityRegistry()
    registry.register(adapter)

    await registry.start()
    await registry.dispatch(
        "test.stateful", ExecutionRequest(capability_id="test.stateful")
    ).result(5)
    health = await registry.health(adapter)
    await registry.close()

    assert health["status"] == "healthy"
    assert adapter.closed
    assert len(adapter.loops) == 4
    assert len(set(adapter.loops)) == 1, "the adapter was reached on more than one event loop"
    assert adapter.loops[0] != id(asyncio.get_running_loop()), (
        "adapter code ran on the calling loop, so a blocking adapter would stall it"
    )


@pytest.mark.asyncio
async def test_a_declared_wait_bounds_a_blocking_adapter_and_leaves_the_loop_free() -> None:
    adapter = BlockingAdapter(seconds=2.0)
    registry = CapabilityRegistry()
    registry.register(adapter)
    call = registry.dispatch("test.blocking", ExecutionRequest(capability_id="test.blocking"))

    started = time.monotonic()
    ticks = 0
    with pytest.raises(TimeoutError):
        waiting = asyncio.create_task(call.result(0.1))
        while not waiting.done():
            await asyncio.sleep(0.01)
            ticks += 1
        await waiting
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, f"the call was abandoned after {elapsed:.3f}s, not 0.1s"
    assert ticks > 1, "the calling loop never ran while the adapter blocked"
    # Abandoning the wait does not stop the work, and nothing in software could. The runtime
    # records that it stopped waiting; a person establishes what the equipment did.
    assert adapter.finished.wait(timeout=5)
    await registry.close()


class UnreachableAdapter(CapabilityAdapter):
    """An adapter that could not open a connection, so the command never left this process."""

    name = "unreachable"

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="test.unreachable",
                name="Unreachable",
                executor_type=ExecutorType.INSTRUMENT,
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise NotDispatchedError("the client could not open a connection to the instrument")


@pytest.mark.asyncio
async def test_a_non_dispatch_claim_survives_the_worker_thread_unchanged() -> None:
    """The claim is carried by the exception's type, and that type crosses two loops to arrive.

    An adapter raises on its own loop, on its own thread; the runtime reads the failure on the
    calling loop after `_bridge` relays it. Retry safety for a conditionally repeatable capability
    is decided entirely by `isinstance` at that far end, so a relay that wrapped or substituted
    the exception would turn a permitted retry into a silent refusal — or, far worse if the
    substitution ever went the other way, a refusal into a permitted repeat.
    """

    adapter = UnreachableAdapter()
    registry = CapabilityRegistry()
    registry.register(adapter)

    with pytest.raises(NotDispatchedError) as raised:
        await registry.dispatch(
            "test.unreachable", ExecutionRequest(capability_id="test.unreachable")
        ).result(5)

    assert "could not open a connection" in str(raised.value)
    # It is a declared OpenSDL failure, not an unhandled defect: an adapter reporting that it
    # never reached the equipment has behaved correctly, and every interface classifies it so.
    assert isinstance(raised.value, OpenSDLError)
    await registry.close()


@pytest.mark.asyncio
async def test_shutting_the_executor_down_is_safe_without_any_dispatch() -> None:
    executor = AdapterExecutor()
    executor.shutdown()
    executor.shutdown()
