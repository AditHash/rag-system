"""Small username/password login backed by PostgreSQL and signed JWTs."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import UUID, uuid4

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from src import config

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_engine():
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")
    return create_engine(config.DATABASE_URL)


def create_users_table() -> None:
    """Create the one small table needed for local user accounts."""
    if len(config.JWT_SECRET) < 32:
        raise RuntimeError("Set JWT_SECRET to a random value of at least 32 characters.")
    with get_engine().begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS app_users (
                id UUID PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                jti UUID PRIMARY KEY,
                expires_at TIMESTAMPTZ NOT NULL
            )
        """))
        connection.execute(text("DELETE FROM revoked_tokens WHERE expires_at < now()"))


def create_user(username: str, password: str) -> dict[str, str]:
    username = username.lower()
    user_id = uuid4()
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO app_users (id, username, password_hash) "
                    "VALUES (:id, :name, :hash)"
                ),
                {"id": user_id, "name": username, "hash": password_hash.hash(password)},
            )
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Username is already taken.") from error
    return {"id": str(user_id), "username": username}


def authenticate_user(username: str, password: str) -> dict[str, str]:
    with get_engine().connect() as connection:
        row = connection.execute(
            text("SELECT id, username, password_hash FROM app_users WHERE username = :name"),
            {"name": username.lower()},
        ).mappings().first()
    if not row or not password_hash.verify(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"id": str(row["id"]), "username": row["username"]}


def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "jti": str(uuid4()),
            "iat": now,
            "exp": now + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
            "iss": "document-qa",
        },
        config.JWT_SECRET,
        algorithm="HS256",
    )


def token_claims(credentials: HTTPAuthorizationCredentials | None) -> dict:
    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = jwt.decode(
            credentials.credentials,
            config.JWT_SECRET,
            algorithms=["HS256"],
            issuer="document-qa",
            options={"require": ["sub", "jti", "iat", "exp", "iss"]},
        )
        UUID(claims["sub"])
        UUID(claims["jti"])
    except (InvalidTokenError, ValueError, TypeError, KeyError) as error:
        raise unauthorized from error
    return claims


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, str]:
    """Return the database user named by a valid, active Bearer token."""
    claims = token_claims(credentials)

    with get_engine().connect() as connection:
        row = connection.execute(
            text("""
                SELECT id, username FROM app_users
                WHERE id = :id
                  AND NOT EXISTS (SELECT 1 FROM revoked_tokens WHERE jti = :jti)
            """),
            {"id": UUID(claims["sub"]), "jti": UUID(claims["jti"])},
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return {"id": str(row["id"]), "username": row["username"]}


def revoke_token(credentials: HTTPAuthorizationCredentials | None) -> None:
    claims = token_claims(credentials)
    with get_engine().begin() as connection:
        connection.execute(
            text("""
                INSERT INTO revoked_tokens (jti, expires_at)
                VALUES (:jti, :expires_at)
                ON CONFLICT DO NOTHING
            """),
            {
                "jti": UUID(claims["jti"]),
                "expires_at": datetime.fromtimestamp(claims["exp"], timezone.utc),
            },
        )
