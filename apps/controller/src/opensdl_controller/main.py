from __future__ import annotations

import argparse
import asyncio
import json
import signal
from pathlib import Path

from .system import OpenSDLSystem


async def _serve(manifest: Path) -> None:
    system = OpenSDLSystem.from_manifest(manifest)
    # A controller starting up is the case reconciliation is for: any run still marked RUNNING was
    # left behind by a previous process. It is asked for explicitly, and what it moved is printed
    # rather than left for someone to discover in the event log.
    reconciled = await system.start(reconcile=True)
    if reconciled:
        print(
            json.dumps(
                {
                    "reconciled_runs": [
                        {"id": run.id, "state": run.state.value, "error": run.error}
                        for run in reconciled
                    ]
                },
                indent=2,
            )
        )
    print(json.dumps(await system.doctor(), indent=2))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signame in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signame, stop.set)
        except NotImplementedError:
            pass
    try:
        await stop.wait()
    finally:
        await system.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the OpenSDL reference controller")
    parser.add_argument("--manifest", type=Path, default=Path("opensdl.yaml"))
    args = parser.parse_args()
    asyncio.run(_serve(args.manifest))


if __name__ == "__main__":
    main()
