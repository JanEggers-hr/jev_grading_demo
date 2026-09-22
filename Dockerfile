FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_HTTP_TIMEOUT=600 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 app && mkdir -p /app && chown app:app /app
USER app
WORKDIR /app

COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY --chown=app:app app.py config.yaml ./
COPY --chown=app:app jevdemo ./jevdemo
COPY --chown=app:app manifesto/mp_v5.json ./manifesto/mp_v5.json
COPY --chown=app:app .streamlit ./.streamlit

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD /app/.venv/bin/python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/jev_grading_demo/_stcore/health', timeout=4).status == 200 else 1)"

CMD ["/app/.venv/bin/streamlit", "run", "app.py", \
     "--server.port", "8501", "--server.address", "0.0.0.0", \
     "--server.baseUrlPath", "jev_grading_demo", "--server.headless", "true"]
