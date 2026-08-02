from opensdl import OpenSDLClient


def test_client_constructs() -> None:
    client = OpenSDLClient("http://localhost:9999")
    client.close()
