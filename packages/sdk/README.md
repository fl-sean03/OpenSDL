# opensdl-sdk

Public Python SDK and HTTP client.

The twin methods mirror the read-only HTTP routes:

```python
with OpenSDLClient("http://127.0.0.1:8000") as client:
    definition = client.twin()
    scene_bytes = client.twin_scene()
    projection = client.twin_run("run-001")
```

`twin_scene()` returns the exact GLB response bytes. The server checks them against the digest in
the configured twin definition before each response.
