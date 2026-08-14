"""Read a suite of tasks from a file.

Tasks are data rather than Python because the suite is the part of a benchmark that has to be
argued with. A number is only worth quoting if the questions behind it can be read, diffed, and
disagreed with by somebody who did not write them, and that is a file in the repository rather than
a list of constructor calls.

Everything here is checked before an agent is started. A suite naming a laboratory that is not
there, or weighting a category no task belongs to, is wrong in a way that costs real money to find
out at the end of a run instead of at the beginning of one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import BenchmarkSuite, BenchmarkTask

API_VERSION = "opensdl.dev/v0alpha1"
KIND = "BenchmarkSuite"

#: Set by the loader from where the file was found. Naming it in the file would let a suite point
#: its laboratory paths anywhere on the machine that ran it.
_LOADER_OWNED = frozenset({"root"})


class SuiteError(ValueError):
    """A suite file that cannot be used as written."""


def _mapping(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SuiteError(f"{what} must be a mapping, found {type(value).__name__}")
    return value


def _check_paths(suite: BenchmarkSuite) -> None:
    """Every task's laboratory is on disk, and its manifest is inside it.

    Checked here rather than left to the first attempt. A suite of twenty tasks whose eleventh
    names a directory that was renamed would otherwise fail an hour in, after the ten before it
    were paid for.
    """
    for task in suite.tasks:
        source = suite.source_for(task)
        if not source.is_dir():
            raise SuiteError(
                f"task {task.id!r} names a laboratory that is not a directory: {source}"
            )
        manifest = source / task.manifest
        if not manifest.is_file():
            raise SuiteError(f"task {task.id!r} names a manifest that is not there: {manifest}")


def _check_ids(suite: BenchmarkSuite) -> None:
    """Task ids are unique.

    A report is keyed by id when it is compared against another run of the same suite. Two tasks
    sharing one would not fail anything — they would quietly be treated as the same question asked
    twice, which is exactly what repeats are supposed to mean.
    """
    seen: set[str] = set()
    duplicated: set[str] = set()
    for task in suite.tasks:
        if task.id in seen:
            duplicated.add(task.id)
        seen.add(task.id)
    if duplicated:
        raise SuiteError(f"task ids must be unique, repeated: {', '.join(sorted(duplicated))}")


def _check_weights(suite: BenchmarkSuite) -> None:
    """Weights name categories that tasks are actually in.

    A misspelled category weighs nothing and takes its tasks out of the headline index with no
    error anywhere. The index would still be a number, which is what makes this worth failing on.
    """
    categories = {task.category for task in suite.tasks}
    unknown = sorted(set(suite.weights) - categories)
    if unknown:
        raise SuiteError(
            f"weights name categories no task is in: {', '.join(unknown)} "
            f"(tasks are in: {', '.join(sorted(categories))})"
        )
    if suite.weights and (unweighted := sorted(categories - set(suite.weights))):
        raise SuiteError(
            "a suite that weights one category weights all of them, missing: "
            f"{', '.join(unweighted)}"
        )


def load_suite(path: Path | str) -> BenchmarkSuite:
    """Read a suite file and check it can be run before anything is run."""

    path = Path(path)
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SuiteError(f"no suite file at {path}") from exc
    except yaml.YAMLError as exc:
        raise SuiteError(f"{path} is not valid YAML: {exc}") from exc

    document = _mapping(document, str(path))
    if document.get("kind") != KIND:
        raise SuiteError(f"{path} is kind {document.get('kind')!r}, expected {KIND!r}")
    if document.get("apiVersion") != API_VERSION:
        raise SuiteError(
            f"{path} declares apiVersion {document.get('apiVersion')!r}, expected {API_VERSION!r}"
        )

    metadata = _mapping(document.get("metadata") or {}, f"{path} metadata")
    spec = _mapping(document.get("spec") or {}, f"{path} spec")
    if owned := _LOADER_OWNED & set(spec):
        raise SuiteError(f"{path} sets {', '.join(sorted(owned))}, which the loader owns")

    try:
        suite = BenchmarkSuite(
            name=metadata.get("name", path.stem),
            version=str(metadata.get("version", "0")),
            description=metadata.get("description", ""),
            weights=spec.get("weights") or {},
            tasks=[BenchmarkTask.model_validate(task) for task in spec.get("tasks") or []],
            root=path.parent.resolve(),
        )
    except ValidationError as exc:
        raise SuiteError(f"{path} does not describe a suite: {exc}") from exc

    _check_ids(suite)
    _check_weights(suite)
    _check_paths(suite)
    return suite
