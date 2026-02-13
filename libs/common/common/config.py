"""
12-Factor configuration helper.

Every service reads its config from environment variables.
This module provides typed helpers that services can use.
"""

from __future__ import annotations

import os


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_int(key: str, default: int = 0) -> int:
    return int(os.environ.get(key, str(default)))


def env_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


# ── Shared defaults ───────────────────────────────────────────────────

KAFKA_BOOTSTRAP_SERVERS = env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
LOG_LEVEL = env("LOG_LEVEL", "INFO")
LOG_FORMAT = env("LOG_FORMAT", "json")
API_KEY = env("API_KEY", "dev-api-key")
