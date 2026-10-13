from sqlalchemy import select

from app import db as dbmod
from app.models import User
from tests.conftest import DONE, make_user, submit, wait_for


def test_register_login_me(client):
    h = make_user(client)
    assert client.get("/api/v1/auth/me", headers=h).json()["email"] == "a@example.com"
    ok = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"})
    assert ok.status_code == 200
    bad = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong-password-xx"})
    assert bad.status_code == 401


def test_password_is_hashed_not_plaintext(client):
    make_user(client)
    with dbmod.session_factory()() as db:
        u = db.scalar(select(User))
        assert "correct-horse-battery" not in u.password_hash and u.password_hash.startswith("scrypt$")


def test_short_password_rejected_and_duplicate_email(client):
    assert client.post("/api/v1/auth/register", json={"email": "x@example.com", "password": "short"}).status_code == 422
    make_user(client)
    dup = client.post("/api/v1/auth/register", json={"email": "A@example.com", "password": "correct-horse-battery"})
    assert dup.status_code == 409


def test_endpoints_require_auth(client):
    for path in ("/api/v1/tasks", "/api/v1/conversations", "/api/v1/tools", "/api/v1/audit"):
        assert client.get(path).status_code == 401
    assert client.get("/api/v1/tasks", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_tampered_token_rejected(client):
    h = make_user(client)
    tok = h["Authorization"].split()[1]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok[:-2]}xx"}).status_code == 401


def test_users_cannot_see_each_others_resources(client, workspace):
    (workspace / "a.txt").write_text("hi")
    a, b = make_user(client, "a@example.com"), make_user(client, "b@example.com")
    tid = submit(client, a, "read a.txt")
    wait_for(client, a, tid, DONE)
    assert client.get(f"/api/v1/tasks/{tid}", headers=b).status_code == 404
    assert client.post(f"/api/v1/tasks/{tid}/cancel", headers=b).status_code == 404
    assert client.get("/api/v1/tasks", headers=b).json()["total"] == 0
    conv = client.get("/api/v1/tasks/" + tid, headers=a).json()["conversation_id"]
    assert client.get(f"/api/v1/conversations/{conv}", headers=b).status_code == 404
    assert client.post("/api/v1/chat", json={"message": "x", "conversation_id": conv}, headers=b).status_code == 404
    assert client.get("/api/v1/audit", headers=b).json()["total"] == 1  # only b's own registration
