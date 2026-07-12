"""Organization-scoped user management (create, update, password changes).

Every mutation is written together with an audit log row in the same
transaction, so the user table and its audit trail can never diverge.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User
from app.services.audit_log import user_admin_event
from app.services.passwords import hash_password, verify_password

ALLOWED_USER_ROLES = {"admin", "reviewer", "uploader"}


class UserAdminError(ValueError):
    pass


class UserAlreadyExistsError(UserAdminError):
    pass


class UserNotFoundError(UserAdminError):
    pass


class InvalidCurrentPasswordError(UserAdminError):
    pass


class LastAdminRoleError(UserAdminError):
    pass


@dataclass(frozen=True)
class CreateUserPayload:
    email: str
    role: str
    password: str


@dataclass(frozen=True)
class UpdateUserPayload:
    email: str | None = None
    role: str | None = None


def list_users(db: Session, *, organization_id: UUID) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.organization_id == organization_id)
            .order_by(User.email.asc())
        )
    )


def create_user(
    db: Session,
    *,
    organization_id: UUID,
    actor_id: UUID,
    payload: CreateUserPayload,
    request_id: str | None = None,
) -> User:
    email = _normalize_email(payload.email)
    role = _normalize_role(payload.role)
    _ensure_email_available(db, email=email)

    user = User(
        organization_id=organization_id,
        email=email,
        role=role,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    # Flush to assign the generated primary key so the audit event can reference
    # the new user's id before the transaction commits.
    db.flush()
    _add_user_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        user_id=user.id,
        action="user.created",
        request_id=request_id,
        metadata={"email": user.email, "role": user.role},
    )
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    *,
    organization_id: UUID,
    actor_id: UUID,
    user_id: UUID,
    payload: UpdateUserPayload,
    request_id: str | None = None,
) -> User:
    user = _get_user_for_org(db, organization_id=organization_id, user_id=user_id)
    changes: dict[str, str] = {}

    if payload.email is not None:
        email = _normalize_email(payload.email)
        if email != user.email:
            _ensure_email_available(db, email=email)
            changes["email"] = email
            user.email = email

    if payload.role is not None:
        role = _normalize_role(payload.role)
        if role != user.role:
            _ensure_not_last_admin_demoted(db, user=user, new_role=role)
            changes["role"] = role
            user.role = role

    # Only touch the DB / write an audit event when something actually changed,
    # so a no-op update stays a true no-op.
    if changes:
        _add_user_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            user_id=user.id,
            action="user.updated",
            request_id=request_id,
            metadata={"changed_fields": sorted(changes), **changes},
        )
        db.commit()
        db.refresh(user)

    return user


def set_user_password(
    db: Session,
    *,
    organization_id: UUID,
    actor_id: UUID,
    user_id: UUID,
    password: str,
    request_id: str | None = None,
) -> User:
    user = _get_user_for_org(db, organization_id=organization_id, user_id=user_id)
    user.password_hash = hash_password(password)
    _add_user_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        user_id=user.id,
        action="user.password_set",
        request_id=request_id,
        metadata={"target_user_id": str(user.id)},
    )
    db.commit()
    db.refresh(user)
    return user


def change_own_password(
    db: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
    request_id: str | None = None,
) -> None:
    # Self-service change requires proving knowledge of the current password;
    # admin-initiated resets (set_user_password) deliberately skip this check.
    if not verify_password(current_password, user.password_hash):
        raise InvalidCurrentPasswordError("Current password is invalid.")

    user.password_hash = hash_password(new_password)
    _add_user_audit(
        db,
        organization_id=user.organization_id,
        actor_id=user.id,
        user_id=user.id,
        action="user.password_changed",
        request_id=request_id,
        metadata={"target_user_id": str(user.id)},
    )
    db.commit()


def _get_user_for_org(db: Session, *, organization_id: UUID, user_id: UUID) -> User:
    # Match on org as well as id so callers can never load or mutate a user
    # belonging to a different tenant.
    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .where(User.organization_id == organization_id)
    )
    if user is None:
        raise UserNotFoundError("User was not found.")
    return user


def _ensure_email_available(db: Session, *, email: str) -> None:
    # Email is unique globally (not per-org) since it is the login identifier.
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise UserAlreadyExistsError("User email already exists.")


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or len(normalized) < 3:
        raise UserAdminError("User email is invalid.")
    return normalized


def _normalize_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ALLOWED_USER_ROLES:
        raise UserAdminError("User role is invalid.")
    return normalized


def _ensure_not_last_admin_demoted(db: Session, *, user: User, new_role: str) -> None:
    # Only relevant when demoting an existing admin; anything else is safe.
    if user.role != "admin" or new_role == "admin":
        return

    # Block removing the final admin so an organization can never be left with
    # nobody able to administer it (permanent lockout).
    admin_count = db.scalar(
        select(func.count(User.id))
        .where(User.organization_id == user.organization_id)
        .where(User.role == "admin")
    )
    if admin_count == 1:
        raise LastAdminRoleError("Cannot remove the last admin from an organization.")


def _add_user_audit(
    db: Session,
    *,
    organization_id: UUID,
    actor_id: UUID,
    user_id: UUID,
    action: str,
    metadata: dict,
    request_id: str | None,
) -> None:
    event = user_admin_event(
        actor_id=actor_id,
        user_id=user_id,
        action=action,
        metadata=metadata,
    )
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=event.actor_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action,
            event_metadata=event.metadata,
            request_id=request_id,
        )
    )
