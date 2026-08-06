import pytest
from pydantic import ValidationError

from opensdl_schemas import CapabilityBinding, LabManifest, TwinConfig


def test_minimal_manifest() -> None:
    manifest = LabManifest.model_validate(
        {
            "apiVersion": "opensdl.dev/v0alpha1",
            "kind": "Laboratory",
            "metadata": {"name": "test-lab", "owner": "test"},
            "spec": {"policy": {"default_effect": "allow"}},
        }
    )
    assert manifest.metadata.name == "test-lab"
    assert manifest.model_dump(by_alias=True)["apiVersion"] == "opensdl.dev/v0alpha1"


def test_manifest_accepts_typed_twin_configuration() -> None:
    manifest = LabManifest.model_validate(
        {
            "apiVersion": "opensdl.dev/v0alpha1",
            "kind": "Laboratory",
            "metadata": {"name": "test-lab", "owner": "test"},
            "spec": {
                "twin": {
                    "definition": "digital-twin/twin.yaml",
                    "viewer_root": "digital-twin/viewer",
                }
            },
        }
    )

    assert manifest.spec.twin == TwinConfig(
        definition="digital-twin/twin.yaml",
        viewer_root="digital-twin/viewer",
    )
    assert manifest.model_dump(mode="json", exclude_none=True)["spec"]["twin"] == {
        "definition": "digital-twin/twin.yaml",
        "viewer_root": "digital-twin/viewer",
    }


def test_a_capability_binding_has_no_configuration_channel() -> None:
    """`config` on a binding was accepted, never read, and looked like an operating envelope.

    `SAFETY.md` asks the deployment to deny requests outside the validated operating domain, so a
    per-capability `config:` is exactly where an operator writes limits. Nothing consumed it. The
    field is gone rather than wired up, because wiring it up means designing an enforcement
    mechanism, and a field that silently absorbs safety configuration is worse than no field.
    """
    assert "config" not in CapabilityBinding.model_fields


def test_a_manifest_that_configures_a_capability_binding_is_rejected_by_name() -> None:
    with pytest.raises(ValidationError) as raised:
        LabManifest.model_validate(
            {
                "apiVersion": "opensdl.dev/v0alpha1",
                "kind": "Laboratory",
                "metadata": {"name": "test-lab", "owner": "test"},
                "spec": {
                    "capabilities": [
                        {
                            "capability": "sim.mix_color",
                            "adapter": "simulated-lab",
                            "config": {"max_temperature_c": 40},
                        }
                    ]
                },
            }
        )

    message = str(raised.value)
    assert "spec.adapters" in message, "the error has to name the channel that does work"
    assert "operating" in message


def test_a_capability_binding_still_accepts_the_fields_it_supports() -> None:
    binding = CapabilityBinding.model_validate(
        {"capability": "sim.mix_color", "adapter": "simulated-lab", "enabled": False}
    )

    assert binding.capability == "sim.mix_color"
    assert binding.adapter == "simulated-lab"
    assert binding.enabled is False
