FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY hn_browser ./hn_browser

CMD ["sh", "-c", ".venv/bin/uvicorn hn_browser.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
