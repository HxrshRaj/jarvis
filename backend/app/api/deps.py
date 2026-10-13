from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import verify_token


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                                 headers={"WWW-Authenticate": "Bearer"})
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized
    user_id = verify_token(authorization[7:].strip())
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise unauthorized
    return user
