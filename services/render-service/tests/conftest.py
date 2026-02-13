"""Test fixtures for render-service."""

import os
import pytest
from unittest.mock import AsyncMock, patch

os.environ["POSTGRES_HOST"] = ""
os.environ["POSTGRES_DB"] = ""
os.environ["API_KEY"] = "test-key"
os.environ["LOG_FORMAT"] = "text"
os.environ["RUNWAY_MODE"] = "stub"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with patch("app.main.start_kafka_producer", new_callable=AsyncMock), \
         patch("app.main.stop_kafka_producer", new_callable=AsyncMock), \
         patch("app.integrations.kafka_consumer.start_consumer", new_callable=AsyncMock), \
         patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()


HEADERS = {"X-API-Key": "test-key"}
