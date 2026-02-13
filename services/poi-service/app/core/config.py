"""POI-service configuration loaded from environment."""

from __future__ import annotations

from common.config import env, env_int

SERVICE_NAME = "poi-service"
SERVICE_PORT = env_int("SERVICE_PORT", 8001)

POSTGRES_HOST = env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = env_int("POSTGRES_PORT", 5432)
POSTGRES_USER = env("POSTGRES_USER", "platform")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", "localdev")
POSTGRES_DB = env("POSTGRES_DB", "poi_service")

KAFKA_BOOTSTRAP_SERVERS = env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = env("KAFKA_TOPIC_POI_EVENTS", "poi.events")


def database_url() -> str:
    return (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}" f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
