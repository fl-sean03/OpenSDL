from __future__ import annotations

import os

import uvicorn

from .app import create_app


def main() -> None:
    uvicorn.run(
        create_app(manifest_path=os.getenv("OPENSDL_MANIFEST", "opensdl.yaml")),
        host=os.getenv("OPENSDL_HOST", "127.0.0.1"),
        port=int(os.getenv("OPENSDL_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
