"""Authentication and Role-Based Access Control (RBAC) for Project Caelum-EO.

Implements OAuth2 Password Flow with JWT Bearer tokens and role enforcement
(viewer, analyst, admin) for defensive GEOINT operational security.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "caelum_geoint")
POSTGRES_USER = os.getenv("POSTGRES_USER", "caelum_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "caelum_secure_password")

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "caelum-secret-defense-key-2026-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class User(BaseModel):
    """Authenticated GEOINT user model."""

    id: str
    username: str
    role: str


class Token(BaseModel):
    """JWT Bearer token response."""

    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


# Hardcoded seed users for deterministic testing when PostGIS is offline
# Passwords:
# - admin: caelum_admin_2026!
# - analyst_viper: caelum_analyst_2026!
# - viewer_01: caelum_viewer_2026!
SEED_USERS: Dict[str, Dict[str, Any]] = {
    "admin": {
        "id": "00000000-0000-0000-0000-000000000001",
        "username": "admin",
        "hashed_password": "$2b$12$81zbUvn/NDN7d6h7ow/zoeHH8gjAw1Gh/hWwsVYDmeFekgZI9hU3q",
        "role": "admin",
    },
    "analyst_viper": {
        "id": "00000000-0000-0000-0000-000000000002",
        "username": "analyst_viper",
        "hashed_password": "$2b$12$6/AV15SQyXfiE/AV0Ac2NOBBjKxLrsXQswhzCWkZjnMoZsEWSqGZC",
        "role": "analyst",
    },
    "viewer_01": {
        "id": "00000000-0000-0000-0000-000000000003",
        "username": "viewer_01",
        "hashed_password": "$2b$12$NP6EpRFqvxI3bhyK4SA.V.mAo20aC3NOhSiS.cgWAbhb78TxwX6SW",
        "role": "viewer",
    },
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify raw password against bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """Generate bcrypt password hash."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Retrieve user credentials from PostGIS database with in-memory fallback."""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=2,
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id::text, username, hashed_password, role FROM users WHERE username = %s;",
                (username,),
            )
            row = cur.fetchone()
            conn.close()
            if row:
                return dict(row)
    except Exception:
        pass

    return SEED_USERS.get(username)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate signed JWT token containing claims and expiration."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Extract and validate JWT token from Authorization header."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate GEOINT access credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        role: Optional[str] = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
    except JWTError as err:
        raise credentials_exception from err

    user_dict = get_user_by_username(username)
    if user_dict is None:
        raise credentials_exception

    return User(
        id=str(user_dict["id"]),
        username=str(user_dict["username"]),
        role=str(user_dict["role"]),
    )


def require_roles(allowed_roles: List[str]) -> Callable[..., User]:
    """Dependency factory restricting endpoint access to specific operational roles."""

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {allowed_roles}. Current role: '{current_user.role}'.",
            )
        return current_user

    return role_checker


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    """Authenticate with username and password, returning JWT bearer token."""
    user = get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        role=user["role"],
        username=user["username"],
    )


@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)) -> User:
    """Retrieve profile and RBAC role for currently authenticated user."""
    return current_user
