from opensdl_schemas import LabManifest


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
