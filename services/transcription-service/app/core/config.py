"""Transcription-service configuration.

Handles both STT (speech-to-text) and TTS (text-to-speech / voiceover).
"""

from common.config import env, env_int

SERVICE_NAME = "transcription-service"
SERVICE_PORT = env_int("SERVICE_PORT", 8004)

POSTGRES_HOST = env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = env_int("POSTGRES_PORT", 5432)
POSTGRES_USER = env("POSTGRES_USER", "platform")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", "localdev")
POSTGRES_DB = env("POSTGRES_DB", "transcription_service")

KAFKA_BOOTSTRAP_SERVERS = env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = env("KAFKA_TOPIC_VIDEO_EVENTS", "video.events")

# ── ElevenLabs TTS ─────────────────────────────────────────────
ELEVENLABS_MODE = env("ELEVENLABS_MODE", "stub")  # 'stub' | 'live'
ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = env("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Default: Rachel


def database_url() -> str:
    return (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}" f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
