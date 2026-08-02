from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from opensdl_storage import ArtifactStore, RepositoryStore


class RunBundleExporter:
    def __init__(self, repositories: RepositoryStore, artifact_store: ArtifactStore) -> None:
        self.repositories = repositories
        self.artifact_store = artifact_store

    def export(self, run_id: str, destination: str | Path) -> Path:
        run = self.repositories.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        tasks = self.repositories.list_tasks(run_id)
        events = self.repositories.list_events(run_id=run_id, limit=None)
        artifacts = self.repositories.list_artifacts(run_id=run_id)
        artifact_metadata = [
            {
                **artifact.model_dump(mode="json"),
                "storage_path": f"artifacts/{artifact.sha256}",
            }
            for artifact in artifacts
        ]
        artifact_files = {
            f"artifacts/{artifact.sha256}": artifact for artifact in artifacts
        }
        target = Path(destination)
        if target.suffix != ".zip":
            target = target / f"{run_id}.zip"
        target.parent.mkdir(parents=True, exist_ok=True)

        crate = {
            "@context": "https://w3id.org/ro/crate/1.1/context",
            "@graph": [
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "about": {"@id": "./"},
                },
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "name": f"OpenSDL run {run_id}",
                    "description": f"Portable execution and provenance bundle for workflow {run.workflow_id}",
                    "hasPart": [
                        {"@id": "run.json"},
                        {"@id": "tasks.json"},
                        {"@id": "events.jsonl"},
                        {"@id": "artifacts.json"},
                        *[{"@id": path} for path in artifact_files],
                    ],
                },
                *[
                    {
                        "@id": path,
                        "@type": "File",
                        "encodingFormat": artifact.media_type,
                        "contentSize": artifact.size_bytes,
                        "sha256": artifact.sha256,
                    }
                    for path, artifact in artifact_files.items()
                ],
            ],
        }
        with ZipFile(target, "w", ZIP_DEFLATED) as archive:
            archive.writestr("ro-crate-metadata.json", json.dumps(crate, indent=2))
            archive.writestr("run.json", run.model_dump_json(indent=2))
            archive.writestr("tasks.json", json.dumps([task.model_dump(mode="json") for task in tasks], indent=2, default=str))
            archive.writestr("events.jsonl", "\n".join(event.model_dump_json() for event in events) + "\n")
            archive.writestr("artifacts.json", json.dumps(artifact_metadata, indent=2))
            for path, artifact in artifact_files.items():
                data = self.artifact_store.read_bytes(artifact)
                archive.writestr(path, data)
        return target
