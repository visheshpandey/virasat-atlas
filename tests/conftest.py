"""Test setup: a temporary SQLite DB and media folder, set before the app is imported."""
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

_tmp = tempfile.mkdtemp(prefix="virasat-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["MEDIA_DIR"] = str(Path(_tmp, "media"))
os.environ["APP_ENV"] = "test"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["SEMANTIC_MODEL"] = ""

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client() -> Iterator:
    """One TestClient for the whole run, so lifespan runs once on one event loop."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def auth_headers(client) -> dict:
    """Register a user and return a bearer header."""
    creds = {"email": "fellow@example.com", "password": "correct-horse"}
    client.post("/api/v1/auth/register", json={"name": "Test Fellow", **creds})
    token = client.post("/api/v1/auth/login", json=creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def pytest_sessionfinish() -> None:
    shutil.rmtree(_tmp, ignore_errors=True)
