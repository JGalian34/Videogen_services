from common.logging import setup_logging
from app.core.config import SERVICE_NAME


def init_logging() -> None:
    setup_logging(SERVICE_NAME)
