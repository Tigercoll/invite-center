FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./

RUN pip install --upgrade pip && \
    pip install fastapi granian pydantic python-dotenv

COPY app ./app
COPY README.md ./
COPY .env.example ./.env.example

RUN mkdir -p /app/data

EXPOSE 8010

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8010", "app.main:app"]
