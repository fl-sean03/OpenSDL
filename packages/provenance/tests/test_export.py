import hashlib
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from opensdl_core import ArtifactKind, ArtifactRecord, EventRecord, RunRecord
from opensdl_provenance import RunBundleExporter
from opensdl_storage import Database, LocalArtifactStore, Repositories


def test_run_bundle_exports_complete_integrity_metadata_without_duplicate_files(
    tmp_path,
) -> None:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    run = repositories.create_run(RunRecord(workflow_id="large-run"))
    occurred_at = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(501):
        repositories.append_event(
            EventRecord(
                type="MeasurementRecorded",
                run_id=run.id,
                occurred_at=occurred_at + timedelta(microseconds=index),
                payload={"index": index},
            )
        )
    artifact_store = LocalArtifactStore(tmp_path / "artifacts", repositories)
    artifact_bytes = b"immutable result"
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    first = artifact_store.put_bytes(
        artifact_bytes,
        media_type="text/plain",
        kind=ArtifactKind.RAW,
        run_id=run.id,
        metadata={"sample": "A"},
    )
    second = artifact_store.put_bytes(
        artifact_bytes,
        media_type="text/plain",
        kind=ArtifactKind.DERIVED,
        run_id=run.id,
        metadata={"sample": "B"},
    )

    target = RunBundleExporter(repositories, artifact_store).export(run.id, tmp_path / "bundle.zip")

    artifact_path = f"artifacts/{digest}"
    with ZipFile(target) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert names.count(artifact_path) == 1
        assert hashlib.sha256(archive.read(artifact_path)).hexdigest() == digest
        events = archive.read("events.jsonl").decode().splitlines()
        assert len(events) == 501
        assert [json.loads(event)["payload"]["index"] for event in events] == list(range(501))

        artifact_metadata = json.loads(archive.read("artifacts.json"))
        assert {item["id"] for item in artifact_metadata} == {first.id, second.id}
        assert {ArtifactRecord.model_validate(item).storage_path for item in artifact_metadata} == {
            artifact_path
        }
        assert {item["metadata"]["sample"] for item in artifact_metadata} == {
            "A",
            "B",
        }

        crate = json.loads(archive.read("ro-crate-metadata.json"))
        dataset = next(item for item in crate["@graph"] if item["@id"] == "./")
        assert {item["@id"] for item in dataset["hasPart"]} >= {
            "artifacts.json",
            artifact_path,
        }
        artifact_file = next(item for item in crate["@graph"] if item["@id"] == artifact_path)
        assert artifact_file["sha256"] == digest
        assert artifact_file["contentSize"] == len(artifact_bytes)
    database.dispose()


@pytest.mark.parametrize(
    "unsafe_run_id",
    ["../escape", r"..\escape", ".", "..", "run id", "r" + "a" * 80],
)
def test_run_bundle_rejects_unsafe_id_before_repository_or_path_access(
    tmp_path,
    unsafe_run_id: str,
) -> None:
    repositories = Mock()
    destination = tmp_path / "exports"

    with pytest.raises(ValueError, match="run ID"):
        RunBundleExporter(repositories, Mock()).export(unsafe_run_id, destination)

    repositories.get_run.assert_not_called()
    assert not destination.exists()
