# API reference

The FastAPI application serves OpenAPI documentation at `/docs`.

Implemented endpoints:

- `GET /health`
- `GET /context`
- `GET /tools`
- `GET /capabilities`
- `POST /capabilities/{capability_id}/execute`
- `GET /resources`
- `GET /runs`
- `POST /runs`
- `GET /runs/{run_id}`
- `GET /events`
- `GET /twin`
- `GET /twin/scene.glb`
- `GET /twin/runs/{run_id}`
- `GET /viewer`
- `GET /viewer/{asset_path}`

The twin and viewer endpoints are read-only and return 404 when the laboratory manifest declares no
digital twin.
