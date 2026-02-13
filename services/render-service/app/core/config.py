"""Render-service configuration."""

from common.config import env, env_int

SERVICE_NAME = "render-service"
SERVICE_PORT = env_int("SERVICE_PORT", 8005)

POSTGRES_HOST = env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = env_int("POSTGRES_PORT", 5432)
POSTGRES_USER = env("POSTGRES_USER", "platform")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", "localdev")
POSTGRES_DB = env("POSTGRES_DB", "render_service")

KAFKA_BOOTSTRAP_SERVERS = env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = env("KAFKA_TOPIC_VIDEO_EVENTS", "video.events")
KAFKA_CONSUMER_GROUP = env("KAFKA_CONSUMER_GROUP", "render-service-group")

# Runway provider
RUNWAY_MODE = env("RUNWAY_MODE", "stub")  # 'stub' | 'live'
RUNWAY_API_KEY = env("RUNWAY_API_KEY", "")
RUNWAY_API_URL = env("RUNWAY_API_URL", "https://api.runwayml.com/v1")


def database_url() -> str:
    return (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}" f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
