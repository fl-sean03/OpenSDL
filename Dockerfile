FROM ghcr.io/astral-sh/uv:0.11.32-python3.12-trixie-slim@sha256:519357e414a4240af8b3ac657466c20f9d6041b5a3ce999d96fa9d576ef7fd29 AS runtime
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY uv.lock pyproject.toml ./
COPY packages ./packages
COPY apps ./apps
COPY adapters ./adapters
COPY domain-packs ./domain-packs
COPY README.md LICENSE ./
RUN uv sync --locked --all-packages --no-dev
COPY examples ./examples
COPY database ./database
EXPOSE 8000
CMD ["uv", "run", "--locked", "--no-sync", "opensdl", "serve-api", "--manifest", "examples/simulated-color-mixing/opensdl.yaml", "--host", "0.0.0.0", "--port", "8000"]
