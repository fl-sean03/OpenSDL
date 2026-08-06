"""Tests for the deployment's control over which plugins a manifest may load.

A manifest names plugins, and loading one imports and executes arbitrary installed code in the
process that talks to equipment. In a laboratory repository where an agent edits the manifest, that
is the shortest path from "a file changed" to "new code runs". Two controls exist:

* **provenance** — a plugin claiming a reference adapter name must come from the reference
  distribution, so a third party cannot squat `simulated-lab` and be loaded in its place;
* **an allowlist** — a deployment can name the plugins a manifest is permitted to bind at all.

The allowlist is deployment-controlled through the environment rather than manifest-controlled,
because the threat is a manifest that was edited. A control a manifest can grant itself is not one.
"""

from types import SimpleNamespace

import pytest

from opensdl_capabilities import plugins
from opensdl_capabilities.plugins import (
    PLUGIN_ALLOWLIST_ENV,
    PluginNotAllowedError,
    enforce_plugin_allowlist,
    plugin_allowlist,
    validate_declared_adapter_plugins,
)


def test_an_unset_allowlist_leaves_every_plugin_permitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed only when the operator asks for it: no variable, no new constraint."""
    monkeypatch.delenv(PLUGIN_ALLOWLIST_ENV, raising=False)

    assert plugin_allowlist() is None
    enforce_plugin_allowlist(["anything-at-all"], None)


def test_the_allowlist_is_a_comma_separated_list_with_surrounding_space_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PLUGIN_ALLOWLIST_ENV, " simulated-lab , local-compute ,, human-task ")

    assert plugin_allowlist() == frozenset({"simulated-lab", "local-compute", "human-task"})


def test_a_listed_plugin_is_permitted_and_an_unlisted_one_is_refused() -> None:
    allowlist = frozenset({"simulated-lab"})

    enforce_plugin_allowlist(["simulated-lab"], allowlist)

    with pytest.raises(PluginNotAllowedError) as raised:
        enforce_plugin_allowlist(["simulated-lab", "vendor-hardware"], allowlist)

    message = str(raised.value)
    assert "vendor-hardware" in message
    assert "simulated-lab" in message, "the refusal has to say what is permitted"
    assert PLUGIN_ALLOWLIST_ENV in message, "and where the constraint came from"


def test_an_explicitly_empty_allowlist_permits_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`OPENSDL_PLUGIN_ALLOWLIST=` is a deliberate instruction, not a missing value.

    Treating it as unset would turn a typo in a deployment's configuration into a silent removal of
    the control, which is the failure mode this whole finding is about.
    """
    monkeypatch.setenv(PLUGIN_ALLOWLIST_ENV, "   ")

    empty = plugin_allowlist()
    assert empty == frozenset()

    with pytest.raises(PluginNotAllowedError, match="permits no plugin"):
        enforce_plugin_allowlist(["simulated-lab"], empty)


def test_declared_plugin_validation_checks_reference_names_and_ignores_the_rest() -> None:
    """A laboratory's own adapter has no reference provenance to check, and must still load."""
    validate_declared_adapter_plugins(["simulated-lab", "my-lab-balance", "local-compute"])


def test_declared_plugin_validation_rejects_a_squatted_reference_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shadow = SimpleNamespace(
        name="simulated-lab",
        value="vendor_hardware.adapter:PhysicalAdapter",
        dist=SimpleNamespace(name="vendor-hardware"),
    )

    def fake_entry_points(*, group: str) -> list[SimpleNamespace]:
        return [shadow] if group == "opensdl.adapters" else []

    monkeypatch.setattr(plugins, "entry_points", fake_entry_points)

    with pytest.raises(LookupError, match="resolved to"):
        validate_declared_adapter_plugins(["simulated-lab", "my-lab-balance"])
