from opensdl_domain_chemistry import Chemical

def test_chemical() -> None:
    assert Chemical(id="water", name="Water").name == "Water"
