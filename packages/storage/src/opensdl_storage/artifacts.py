from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from opensdl_core import ArtifactKind, ArtifactRecord

from .repositories import Repositories


class LocalArtifactStore:
    def __init__(self, root: str | Path, repositories: Repositories) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.repositories = repositories

    def put_bytes(
        self,
        data: bytes,
        *,
        media_type: str,
        kind: ArtifactKind = ArtifactKind.OTHER,
        run_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / "sha256" / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        record = ArtifactRecord(
            sha256=digest,
            media_type=media_type,
            size_bytes=len(data),
            kind=kind,
            storage_path=str(path),
            run_id=run_id,
            task_id=task_id,
            metadata=metadata or {},
        )
        return self.repositories.add_artifact(record)

    def put_json(self, value: Any, **kwargs: Any) -> ArtifactRecord:
        data = json.dumps(value, indent=2, sort_keys=True, default=str).encode("utf-8")
        return self.put_bytes(data, media_type="application/json", **kwargs)

    def read_bytes(self, artifact: ArtifactRecord) -> bytes:
        data = Path(artifact.storage_path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != artifact.sha256:
            raise ValueError(f"artifact hash mismatch for {artifact.id}")
        return data
