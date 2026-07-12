from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_roles
from app.api.errors import api_error, conflict_error
from app.db.session import get_db
from app.models.user import User
from app.services.user_admin import (
    CreateUserPayload,
    InvalidCurrentPasswordError,
    LastAdminRoleError,
    UpdateUserPayload,
    UserAdminError,
    UserAlreadyExistsError,
    UserNotFoundError,
    change_own_password,
    create_user,
    list_users,
    set_user_password,
    update_user,
)

router = APIRouter(prefix="/users", tags=["users"])


class UserResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    email: str
    role: str


class UserListResponse(BaseModel):
    users: list[UserResponse]


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=12, max_length=256)


class UpdateUserRequest(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    role: str | None = Field(default=None, min_length=1, max_length=50)


class SetPasswordRequest(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


@router.get("", response_model=UserListResponse)
def list_user_records(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
) -> UserListResponse:
    return UserListResponse(
        users=[_to_user_response(user) for user in list_users(db, organization_id=current_user.organization_id)]
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_record(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> UserResponse:
    try:
        user = create_user(
            db,
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            payload=CreateUserPayload(
                email=payload.email,
                role=payload.role,
                password=payload.password,
            ),
            request_id=request_id,
        )
    except UserAlreadyExistsError as exc:
        raise conflict_error("user_duplicate", str(exc), request_id=request_id) from exc
    except UserAdminError as exc:
        raise conflict_error("user_invalid", str(exc), request_id=request_id) from exc

    return _to_user_response(user)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_current_user_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> None:
    try:
        change_own_password(
            db,
            user=current_user,
            current_password=payload.current_password,
            new_password=payload.new_password,
            request_id=request_id,
        )
    except InvalidCurrentPasswordError as exc:
        raise api_error(
            http_status=status.HTTP_401_UNAUTHORIZED,
            code="invalid_current_password",
            message=str(exc),
            request_id=request_id,
        ) from exc
    except UserAdminError as exc:
        raise conflict_error("user_invalid", str(exc), request_id=request_id) from exc


@router.patch("/{user_id}", response_model=UserResponse)
def update_user_record(
    user_id: UUID,
    payload: UpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> UserResponse:
    try:
        user = update_user(
            db,
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            user_id=user_id,
            payload=UpdateUserPayload(email=payload.email, role=payload.role),
            request_id=request_id,
        )
    except UserNotFoundError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="user_not_found",
            message=str(exc),
            request_id=request_id,
        ) from exc
    except UserAlreadyExistsError as exc:
        raise conflict_error("user_duplicate", str(exc), request_id=request_id) from exc
    except LastAdminRoleError as exc:
        raise conflict_error("last_admin_required", str(exc), request_id=request_id) from exc
    except UserAdminError as exc:
        raise conflict_error("user_invalid", str(exc), request_id=request_id) from exc

    return _to_user_response(user)


@router.post("/{user_id}/password", response_model=UserResponse)
def set_user_password_record(
    user_id: UUID,
    payload: SetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> UserResponse:
    try:
        user = set_user_password(
            db,
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            user_id=user_id,
            password=payload.password,
            request_id=request_id,
        )
    except UserNotFoundError as exc:
        raise api_error(
            http_status=status.HTTP_404_NOT_FOUND,
            code="user_not_found",
            message=str(exc),
            request_id=request_id,
        ) from exc
    except UserAdminError as exc:
        raise conflict_error("user_invalid", str(exc), request_id=request_id) from exc

    return _to_user_response(user)


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        role=user.role,
    )
