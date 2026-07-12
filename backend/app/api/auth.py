import base64
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Cookie, Depends, Header, Response, status
from pydantic import BaseModel, Field
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import api_error
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.passwords import verify_password

logger = structlog.get_logger("app.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
_REVOKED_PREFIX = "revoked_jwt"


class AuthenticationError(ValueError):
    pass


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: UUID
    organization_id: UUID
    email: str
    role: str


class SessionResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    email: str
    role: str


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise api_error(
            http_status=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            message="Email or password is invalid.",
        )

    expires_in = settings.jwt_access_token_ttl_seconds
    access_token = create_access_token(user, expires_in=expires_in)
    refresh_token = create_refresh_token(user)
    # httpOnly cookies keep tokens out of JS reach (XSS-resistant); the body
    # token is retained for non-browser API clients.
    _set_auth_cookies(response, access_token, refresh_token)
    return LoginResponse(
        access_token=access_token,
        expires_in=expires_in,
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        role=user.role,
    )


@router.post("/refresh", response_model=SessionResponse)
def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db: Session = Depends(get_db),
) -> SessionResponse:
    try:
        claims = _decode_hs256_jwt(refresh_token) if refresh_token else None
        if not claims or claims.get("type") != "refresh":
            raise AuthenticationError("A valid refresh token is required.")
        if _is_revoked(claims.get("jti")):
            raise AuthenticationError("Refresh token has been revoked.")
        user_id = _subject_uuid(claims)
    except AuthenticationError as exc:
        raise api_error(
            http_status=status.HTTP_401_UNAUTHORIZED,
            code="authentication_required",
            message=str(exc),
        ) from exc

    user = db.get(User, user_id)
    if user is None:
        raise api_error(
            http_status=status.HTTP_401_UNAUTHORIZED,
            code="authentication_required",
            message="Authenticated user was not found.",
        )

    # Rotate: revoke the presented refresh token and issue a fresh pair.
    _revoke(claims)
    access_token = create_access_token(user)
    new_refresh = create_refresh_token(user)
    _set_auth_cookies(response, access_token, new_refresh)
    return SessionResponse(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        role=user.role,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> Response:
    for token in (access_token, refresh_token):
        if token:
            try:
                _revoke(_decode_hs256_jwt(token))
            except AuthenticationError:
                pass  # already invalid/expired: nothing to revoke
    _clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    token = _bearer_token(authorization) or access_token
    try:
        claims = _authenticate_access_token(token)
        user_id = _subject_uuid(claims)
    except AuthenticationError as exc:
        raise api_error(
            http_status=status.HTTP_401_UNAUTHORIZED,
            code="authentication_required",
            message=str(exc),
        ) from exc

    user = db.get(User, user_id)
    if user is None:
        raise api_error(
            http_status=status.HTTP_401_UNAUTHORIZED,
            code="authentication_required",
            message="Authenticated user was not found.",
        )

    return user


def require_roles(*allowed_roles: str) -> Callable[[User], User]:
    allowed = {role.lower() for role in allowed_roles}

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.lower() not in allowed:
            raise api_error(
                http_status=status.HTTP_403_FORBIDDEN,
                code="permission_denied",
                message="User does not have permission to perform this action.",
            )
        return current_user

    return dependency


@router.get("/me", response_model=SessionResponse)
def read_session(current_user: User = Depends(get_current_user)) -> SessionResponse:
    return SessionResponse(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        email=current_user.email,
        role=current_user.role,
    )


def _authenticate_access_token(token: str | None) -> dict:
    if not token:
        raise AuthenticationError("Authentication credentials are required.")
    claims = _decode_hs256_jwt(token)
    # A refresh token must not be usable as an access token.
    if claims.get("type") == "refresh":
        raise AuthenticationError("Token is not an access token.")
    if _is_revoked(claims.get("jti")):
        raise AuthenticationError("Token has been revoked.")
    return claims


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Authorization bearer token is required.")
    return token


def _subject_uuid(claims: dict) -> UUID:
    subject = claims.get("sub")
    if not subject:
        raise AuthenticationError("Token subject is required.")
    try:
        return UUID(str(subject))
    except ValueError as exc:
        raise AuthenticationError("Token subject is invalid.") from exc


def _decode_hs256_jwt(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationError("Token is invalid.")

    encoded_header, encoded_payload, encoded_signature = parts
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    supplied_signature = _urlsafe_b64decode(encoded_signature)
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise AuthenticationError("Token signature is invalid.")

    try:
        header = json.loads(_urlsafe_b64decode(encoded_header))
        claims = json.loads(_urlsafe_b64decode(encoded_payload))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthenticationError("Token is invalid.") from exc

    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise AuthenticationError("Token algorithm is unsupported.")

    expires_at = claims.get("exp")
    if not isinstance(expires_at, int | float):
        raise AuthenticationError("Token expiry is required.")
    if expires_at <= time.time():
        raise AuthenticationError("Token has expired.")

    return claims


def create_access_token(user: User, *, expires_in: int | None = None) -> str:
    expires_in = expires_in or settings.jwt_access_token_ttl_seconds
    return _encode_hs256_jwt(
        {
            "sub": str(user.id),
            "org": str(user.organization_id),
            "role": user.role,
            "email": user.email,
            "type": "access",
            "jti": uuid4().hex,
            "iat": int(time.time()),
            "exp": int(time.time()) + expires_in,
        }
    )


def create_refresh_token(user: User, *, expires_in: int | None = None) -> str:
    expires_in = expires_in or settings.jwt_refresh_token_ttl_seconds
    return _encode_hs256_jwt(
        {
            "sub": str(user.id),
            "type": "refresh",
            "jti": uuid4().hex,
            "iat": int(time.time()),
            "exp": int(time.time()) + expires_in,
        }
    )


def _encode_hs256_jwt(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _urlsafe_b64encode_json(header)
    encoded_payload = _urlsafe_b64encode_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_payload}.{_urlsafe_b64encode(signature)}"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.jwt_access_token_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.jwt_refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/", httponly=True, samesite=settings.cookie_samesite)


def _revocation_client() -> Redis:
    return Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)


def _revoke(claims: dict) -> None:
    jti = claims.get("jti")
    if not jti:
        return
    ttl = int(claims.get("exp", 0) - time.time())
    if ttl <= 0:
        return
    try:
        _revocation_client().setex(f"{_REVOKED_PREFIX}:{jti}", ttl, "1")
    except RedisError as exc:
        logger.warning("auth.revoke_failed", error=str(exc))


def _is_revoked(jti: str | None) -> bool:
    if not jti:
        return False
    try:
        return _revocation_client().exists(f"{_REVOKED_PREFIX}:{jti}") == 1
    except RedisError as exc:
        # Fail open on cache outage so authentication stays available.
        logger.warning("auth.revocation_check_failed", error=str(exc))
        return False


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise AuthenticationError("Token is invalid.") from exc


def _urlsafe_b64encode_json(value: dict) -> str:
    return _urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
