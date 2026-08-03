from opensdl_schemas import LabManifest, TwinConfig


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
