from opensdl_domain_materials import Composition, get_pack

def test_materials_pack() -> None:
    assert Composition(components={"Fe":0.7,"Ni":0.3}).basis == "mole_fraction"
    assert "Specimen" in get_pack()["models"]
