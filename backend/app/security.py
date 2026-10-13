"""Password hashing (scrypt) and signed session tokens using only the standard library."""
import base64
import hashlib
import hmac
import json
import os
import time

from app.config import get_settings


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(get_settings().secret_key.encode(), payload.encode(), hashlib.sha256).digest())


def create_token(user_id: str) -> str:
    body = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + get_settings().token_ttl_seconds}).encode())
    return f"{body}.{_sign(body)}"


def verify_token(token: str) -> str | None:
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(body)):
            return None
        data = json.loads(_unb64(body))
        return data["sub"] if data["exp"] > time.time() else None
    except Exception:
        return None
