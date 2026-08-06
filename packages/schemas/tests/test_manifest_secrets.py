"""A manifest names its credentials; it does not carry them.

`docs/concepts/manifests.md` has always said credentials arrive "through environment variables or a
secret provider". Neither existed: `load_manifest` read YAML and validated it, so the only way to
give a real instrument a password was to type the password into `opensdl.yaml` — the file every
document tells a laboratory to commit. These tests pin the mechanism that makes the sentence true,
and the three ways it refuses rather than guesses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from opensdl_schemas import (
    LabManifest,
    ManifestSecretError,
    dump_manifest,
    load_manifest,
    redacted_manifest_document,
)


def write(tmp_path: Path, spec: dict[str, Any]) -> Path:
    document = {
        "apiVersion": "opensdl.dev/v0alpha1",
        "kind": "Laboratory",
        "metadata": {"name": "secret-lab", "owner": "test"},
        "spec": spec,
    }
    path = tmp_path / "opensdl.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_an_environment_reference_in_adapter_configuration_is_resolved_at_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BALANCE_TOKEN", "s3cr3t-token")
    path = write(
        tmp_path,
        {
            "adapters": [
                {
                    "name": "balance",
                    "plugin": "networked-balance",
                    "config": {"token": "${env:BALANCE_TOKEN}", "host": "balance.lab"},
                }
            ]
        },
    )

    manifest = load_manifest(path)

    assert manifest.spec.adapters[0].config == {"token": "s3cr3t-token", "host": "balance.lab"}


def test_a_reference_inside_a_larger_string_is_resolved_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The database URL is the case: the credential is one field of a longer string."""
    monkeypatch.setenv("PGPASSWORD", "hunter2")
    path = write(
        tmp_path,
        {"storage": {"database": {"url": "postgresql://opensdl:${env:PGPASSWORD}@db:5432/lab"}}},
    )

    manifest = load_manifest(path)

    assert manifest.spec.storage.database.url == "postgresql://opensdl:hunter2@db:5432/lab"


def test_an_unset_variable_fails_closed_and_names_the_variable(tmp_path: Path) -> None:
    """The failure a laboratory must not have is the silent one.

    An unresolved credential that becomes `""` authenticates against nothing and surfaces as a
    login failure at an instrument, which is a far worse place to learn that a variable was
    misspelled. The reference is never left as literal text either: an adapter handed the string
    `${env:BALANCE_TOKEN}` sends it as the password.
    """
    path = write(
        tmp_path,
        {
            "adapters": [
                {"name": "balance", "plugin": "b", "config": {"token": "${env:BALANCE_TOKEN}"}}
            ]
        },
    )

    with pytest.raises(ManifestSecretError) as raised:
        load_manifest(path)

    message = str(raised.value)
    assert "BALANCE_TOKEN" in message
    assert "spec.adapters[0].config.token" in message


def test_a_variable_that_is_set_but_empty_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BALANCE_TOKEN", "")
    path = write(
        tmp_path,
        {
            "adapters": [
                {"name": "balance", "plugin": "b", "config": {"token": "${env:BALANCE_TOKEN}"}}
            ]
        },
    )

    with pytest.raises(ManifestSecretError) as raised:
        load_manifest(path)

    assert "BALANCE_TOKEN" in str(raised.value)
    assert "empty" in str(raised.value)


def test_an_unimplemented_provider_is_refused_and_names_the_one_that_exists(
    tmp_path: Path,
) -> None:
    """`${...}` is a scheme, not a single feature. One prefix is implemented; the rest say so."""
    path = write(
        tmp_path,
        {"adapters": [{"name": "b", "plugin": "b", "config": {"token": "${vault:lab/token}"}}]},
    )

    with pytest.raises(ManifestSecretError) as raised:
        load_manifest(path)

    message = str(raised.value)
    assert "vault" in message
    assert "env:" in message


def test_a_placeholder_that_names_no_provider_is_left_alone(tmp_path: Path) -> None:
    """Workflow references such as `${inputs.x}` are not secret references and are not touched."""
    path = write(
        tmp_path,
        {"extensions": {"note": "${inputs.sample_id} and ${steps.mix.output.rgb}"}},
    )

    manifest = load_manifest(path)

    assert manifest.spec.extensions["note"] == "${inputs.sample_id} and ${steps.mix.output.rgb}"


def test_a_reference_in_a_mapping_key_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reference resolves a value. A key naming a variable renames the field it configures."""
    monkeypatch.setenv("FIELD", "token")
    path = write(
        tmp_path,
        {"adapters": [{"name": "b", "plugin": "b", "config": {"${env:FIELD}": "x"}}]},
    )

    with pytest.raises(ManifestSecretError) as raised:
        load_manifest(path)

    assert "key" in str(raised.value)


def test_a_reference_inside_the_policy_block_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Policy is the one subtree where an environment variable would be an authorization decision.

    `default_effect: ${env:EFFECT}` makes `EFFECT=allow` a supported configuration for a live
    laboratory, and `SECURITY.md` names authorization bypass the first vulnerability class. Every
    other field is configuration; this one decides whether a hazardous capability may run.
    """
    monkeypatch.setenv("EFFECT", "allow")
    path = write(tmp_path, {"policy": {"default_effect": "${env:EFFECT}"}})

    with pytest.raises(ManifestSecretError) as raised:
        load_manifest(path)

    message = str(raised.value)
    assert "spec.policy.default_effect" in message
    assert "policy" in message


def test_a_resolved_secret_is_written_back_as_its_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolving at load must not turn a round-trip into a credential commit.

    `dump_manifest` is public API. Load-then-dump would otherwise take a credential out of the
    environment and write it into the file the documentation designates as belonging in Git.
    """
    monkeypatch.setenv("BALANCE_TOKEN", "s3cr3t-token")
    monkeypatch.setenv("PGPASSWORD", "hunter2")
    path = write(
        tmp_path,
        {
            "storage": {"database": {"url": "postgresql://opensdl:${env:PGPASSWORD}@db:5432/lab"}},
            "adapters": [{"name": "b", "plugin": "b", "config": {"token": "${env:BALANCE_TOKEN}"}}],
        },
    )
    manifest = load_manifest(path)
    assert manifest.spec.adapters[0].config["token"] == "s3cr3t-token"

    target = tmp_path / "round-trip.yaml"
    dump_manifest(manifest, target)
    written = target.read_text(encoding="utf-8")

    assert "s3cr3t-token" not in written
    assert "hunter2" not in written
    assert "${env:BALANCE_TOKEN}" in written
    assert "postgresql://opensdl:${env:PGPASSWORD}@db:5432/lab" in written


def test_the_redacted_document_is_what_every_printing_surface_should_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PACK_KEY", "pack-secret")
    path = write(
        tmp_path,
        {
            "domain_packs": [
                {"name": "materials", "plugin": "materials", "config": {"key": "${env:PACK_KEY}"}}
            ]
        },
    )
    manifest = load_manifest(path)
    assert manifest.spec.domain_packs[0].config["key"] == "pack-secret"

    document = redacted_manifest_document(manifest)

    assert document["spec"]["domain_packs"][0]["config"]["key"] == "${env:PACK_KEY}"
    assert "pack-secret" not in str(document)


def test_a_manifest_with_no_references_dumps_exactly_as_before(tmp_path: Path) -> None:
    manifest = LabManifest.model_validate(
        {
            "apiVersion": "opensdl.dev/v0alpha1",
            "kind": "Laboratory",
            "metadata": {"name": "plain", "owner": "test"},
            "spec": {"adapters": [{"name": "b", "plugin": "b", "config": {"seed": 7}}]},
        }
    )
    target = tmp_path / "plain.yaml"

    dump_manifest(manifest, target)

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == manifest.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )


def test_a_validation_failure_does_not_echo_the_resolved_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pydantic prints the input it rejected. A resolved credential must not be that input.

    The CLI's error boundary prints an exception's message verbatim on stderr, so a secret that
    reaches a `ValidationError` reaches the terminal and the shell's scrollback.
    """
    monkeypatch.setenv("CONCURRENCY", "s3cr3t-token")
    path = write(tmp_path, {"runtime": {"max_concurrency": "${env:CONCURRENCY}"}})

    with pytest.raises(ValueError) as raised:
        load_manifest(path)

    message = str(raised.value)
    assert "s3cr3t-token" not in message
    assert "${env:CONCURRENCY}" in message
