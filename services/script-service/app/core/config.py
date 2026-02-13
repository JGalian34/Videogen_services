"""Script-service configuration."""

from common.config import env, env_int

SERVICE_NAME = "script-service"
SERVICE_PORT = env_int("SERVICE_PORT", 8003)

POSTGRES_HOST = env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = env_int("POSTGRES_PORT", 5432)
POSTGRES_USER = env("POSTGRES_USER", "platform")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", "localdev")
POSTGRES_DB = env("POSTGRES_DB", "script_service")

KAFKA_BOOTSTRAP_SERVERS = env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = env("KAFKA_TOPIC_VIDEO_EVENTS", "video.events")

POI_SERVICE_URL = env("POI_SERVICE_URL", "http://localhost:8001")
ASSET_SERVICE_URL = env("ASSET_SERVICE_URL", "http://localhost:8002")

NLP_PROVIDER = env("NLP_PROVIDER", "stub")  # 'stub' | 'openai'


def database_url() -> str:
    return (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}" f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
