import time

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod
from app.config import get_settings
from app.llm.providers import set_provider_override
from app.main import create_app
from app.services.engine import engine


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    s = get_settings()
    s.workspace_root = ws
    s.rate_limit_per_minute = 100_000
    return ws


@pytest.fixture
def client(tmp_path, workspace):
    dbmod.init_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    set_provider_override(None)
    app = create_app()
    with TestClient(app) as c:
        yield c
    engine.wait_idle(10)


def make_user(client, email="a@example.com"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return make_user(client)


def submit(client, auth, message, **kw):
    r = client.post("/api/v1/chat", json={"message": message, **kw}, headers=auth)
    assert r.status_code == 202, r.text
    return r.json()["task_id"]


def wait_for(client, auth, task_id, states, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        t = client.get(f"/api/v1/tasks/{task_id}", headers=auth).json()
        if t["status"] in states:
            return t
        time.sleep(0.05)
    raise AssertionError(f"task stuck in {t['status']}")


DONE = {"succeeded", "failed", "cancelled", "partially_completed"}
