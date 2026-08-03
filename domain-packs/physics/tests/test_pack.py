from opensdl_domain_physics import Signal


def test_signal() -> None:
    assert Signal(name="voltage", values=[1, 2], unit="V").unit == "V"
