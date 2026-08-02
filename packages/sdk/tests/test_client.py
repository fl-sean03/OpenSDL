import opensdl
from opensdl import OpenSDLClient


def test_client_constructs() -> None:
    client = OpenSDLClient("http://localhost:9999")
    client.close()


def test_sdk_exports_core_contracts() -> None:
    assert "RunRecord" in opensdl.__all__
    assert opensdl.RunRecord is not None
