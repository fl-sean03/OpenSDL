FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml ./
COPY packages ./packages
COPY apps ./apps
COPY adapters ./adapters
COPY domain-packs ./domain-packs
COPY README.md LICENSE ./
RUN uv sync --all-packages --no-dev
COPY examples ./examples
COPY database ./database
EXPOSE 8000
CMD ["uv", "run", "opensdl", "serve-api", "--manifest", "examples/simulated-color-mixing/opensdl.yaml", "--host", "0.0.0.0", "--port", "8000"]
