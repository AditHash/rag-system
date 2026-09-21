FROM ghcr.io/astral-sh/uv:0.12.17 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "addroit_docqa.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
