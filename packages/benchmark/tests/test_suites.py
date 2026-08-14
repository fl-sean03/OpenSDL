"""A suite file that cannot be run has to say so before anything is run.

Every case here is a mistake somebody will make while writing tasks. What they have in common is
that none of them would raise on its own: a missing laboratory fails at the eleventh task, a
misspelled weight silently drops a category out of the headline number, and a duplicated id turns
two questions into one. All of them produce a number. That is what makes them worth failing on.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from opensdl_benchmark import SuiteError, load_suite

MINIMAL_TASK = {
    "id": "mix",
    "category": "operate",
    "prompt": "mix one sample",
    "laboratory": "lab",
    "manifest": "opensdl.yaml",
    "checks": [{"kind": "runs_completed", "description": "one run"}],
}


def _write(tmp_path: Path, spec: dict, *, metadata: dict | None = None, **document) -> Path:
    path = tmp_path / "suite.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "opensdl.dev/v0alpha1",
                "kind": "BenchmarkSuite",
                "metadata": metadata or {"name": "example", "version": "1"},
                "spec": spec,
                **document,
            }
        )
    )
    return path


@pytest.fixture
def laboratory(tmp_path: Path) -> Path:
    lab = tmp_path / "lab"
    lab.mkdir()
    (lab / "opensdl.yaml").write_text("kind: Laboratory\n")
    return lab


def test_a_suite_resolves_its_laboratories_against_its_own_directory(
    tmp_path: Path, laboratory: Path
) -> None:
    suite = load_suite(_write(tmp_path, {"tasks": [MINIMAL_TASK]}))

    assert suite.name == "example"
    assert suite.version == "1"
    assert suite.source_for(suite.tasks[0]) == laboratory.resolve()


def test_a_laboratory_that_is_not_there_fails_at_load(tmp_path: Path) -> None:
    """Before an agent is started, rather than after the ten tasks before it were paid for."""

    with pytest.raises(SuiteError, match="not a directory"):
        load_suite(_write(tmp_path, {"tasks": [MINIMAL_TASK]}))


def test_a_manifest_that_is_not_there_fails_at_load(tmp_path: Path, laboratory: Path) -> None:
    (laboratory / "opensdl.yaml").unlink()

    with pytest.raises(SuiteError, match="manifest that is not there"):
        load_suite(_write(tmp_path, {"tasks": [MINIMAL_TASK]}))


def test_duplicate_task_ids_are_refused(tmp_path: Path, laboratory: Path) -> None:
    """Two tasks sharing an id are not two questions, they are one question asked twice."""

    with pytest.raises(SuiteError, match="unique"):
        load_suite(_write(tmp_path, {"tasks": [MINIMAL_TASK, dict(MINIMAL_TASK)]}))


def test_a_weight_naming_no_category_is_refused(tmp_path: Path, laboratory: Path) -> None:
    """The misspelling that would weigh nothing and take its tasks out of the index in silence."""

    with pytest.raises(SuiteError, match="no task is in"):
        load_suite(_write(tmp_path, {"weights": {"operator": 1.0}, "tasks": [MINIMAL_TASK]}))


def test_weighting_one_category_means_weighting_all_of_them(
    tmp_path: Path, laboratory: Path
) -> None:
    """Adding a category and forgetting to weight it would drop it out of the headline number."""

    restraint = MINIMAL_TASK | {"id": "restrain", "category": "restraint"}
    with pytest.raises(SuiteError, match="missing: restraint"):
        load_suite(
            _write(tmp_path, {"weights": {"operate": 1.0}, "tasks": [MINIMAL_TASK, restraint]})
        )


def test_a_suite_cannot_name_its_own_root(tmp_path: Path, laboratory: Path) -> None:
    """Task paths resolve against where the file was found, and a file cannot say otherwise.

    A suite is written by whoever supplies the tasks, which on a shared benchmark is not the person
    running it. Reading `root` out of the document would let it point anywhere on that machine.
    """
    with pytest.raises(SuiteError, match="the loader owns"):
        load_suite(_write(tmp_path, {"root": "/etc", "tasks": [MINIMAL_TASK]}))


def test_the_wrong_kind_of_document_is_refused_by_name(tmp_path: Path, laboratory: Path) -> None:
    """Pointing at a laboratory manifest by mistake is the likely way to get here."""

    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump({"apiVersion": "opensdl.dev/v0alpha1", "kind": "Laboratory"}))

    with pytest.raises(SuiteError, match="expected 'BenchmarkSuite'"):
        load_suite(path)


def test_an_unknown_api_version_is_refused(tmp_path: Path, laboratory: Path) -> None:
    path = _write(tmp_path, {"tasks": [MINIMAL_TASK]})
    document = yaml.safe_load(path.read_text())
    document["apiVersion"] = "opensdl.dev/v9"
    path.write_text(yaml.safe_dump(document))

    with pytest.raises(SuiteError, match="apiVersion"):
        load_suite(path)


def test_an_unknown_check_kind_names_the_suite_rather_than_raising_a_pydantic_error(
    tmp_path: Path, laboratory: Path
) -> None:
    broken = MINIMAL_TASK | {"checks": [{"kind": "vibes_were_good", "description": "hmm"}]}

    with pytest.raises(SuiteError, match="does not describe a suite"):
        load_suite(_write(tmp_path, {"tasks": [broken]}))


def test_a_suite_with_no_tasks_is_not_a_suite(tmp_path: Path) -> None:
    with pytest.raises(SuiteError, match="does not describe a suite"):
        load_suite(_write(tmp_path, {"tasks": []}))


def test_a_missing_file_says_so_plainly(tmp_path: Path) -> None:
    with pytest.raises(SuiteError, match="no suite file"):
        load_suite(tmp_path / "absent.yaml")


def test_a_file_that_is_not_yaml_says_so_plainly(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text("kind: [unclosed\n")

    with pytest.raises(SuiteError, match="not valid YAML"):
        load_suite(path)
