"""`opensdl migrate` — bringing a laboratory's store to the schema the code expects.

The command deliberately does not compose the laboratory: an adapter that fails to import must not
stand between a store and its schema. `--check` writes nothing at all, which for SQLite means it
must not connect, because connecting creates the file.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import opensdl_cli.main as cli

EXAMPLE = Path(__file__).parents[3] / "examples" / "simulated-color-mixing"


def _lab(tmp_path: Path) -> Path:
    root = tmp_path / "lab"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".opensdl", "__pycache__"))
    return root / "opensdl.yaml"


def test_check_reports_a_laboratory_that_has_never_run_without_creating_its_store(
    tmp_path: Path,
) -> None:
    manifest = _lab(tmp_path)

    result = CliRunner().invoke(cli.app, ["migrate", "--manifest", str(manifest), "--check"])

    assert result.exit_code == cli.EXIT_FAILED, result.output
    report = json.loads(result.stdout)
    assert report["current"] is None
    assert report["pending"] == [report["head"]]
    assert report["exists"] is False
    assert not (manifest.parent / ".opensdl" / "opensdl.db").exists()


def test_migrate_creates_the_store_at_head_and_then_checks_clean(tmp_path: Path) -> None:
    manifest = _lab(tmp_path)

    applied = CliRunner().invoke(cli.app, ["migrate", "--manifest", str(manifest)])
    assert applied.exit_code == 0, applied.output
    report = json.loads(applied.stdout)
    assert report["applied"]
    assert report["current"] == report["head"]

    checked = CliRunner().invoke(cli.app, ["migrate", "--manifest", str(manifest), "--check"])
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.stdout)["pending"] == []


def test_a_migration_failure_is_a_refusal_rather_than_a_defect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alembic's `CommandError` reads as an internal defect unless the taxonomy names it.

    It is matched by its full module path, not by the bare name: `CommandError` is a name several
    libraries use, and mapping all of them here would report a genuine defect in OpenSDL as an
    ordinary refusal and suppress the traceback hint that goes with `EXIT_INTERNAL`.
    """
    from alembic.util import CommandError

    manifest = _lab(tmp_path)

    def refuse(_: object) -> dict[str, object]:
        raise CommandError("Can't locate revision identified by 'deadbeef'")

    monkeypatch.setattr(cli.migrate_laboratory, "upgrade", refuse)

    result = CliRunner().invoke(cli.app, ["migrate", "--manifest", str(manifest)])

    assert result.exit_code == cli.EXIT_FAILED, result.output
    assert "Traceback" not in result.output
    assert "deadbeef" in result.stderr
    assert result.stderr.startswith("Failed:")


def test_an_unqualified_name_does_not_borrow_another_librarys_classification() -> None:
    """A third party's `CommandError` must still read as a defect, because it is one."""

    class CommandError(Exception):
        """A collision, defined here in a module OpenSDL's table does not name."""

    assert cli._classify(CommandError("unrelated")) == (cli.EXIT_INTERNAL, "Internal error")
