#!/usr/bin/env python
import argparse
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.organization import Organization
from app.models.user import User
from app.services.passwords import PasswordHashError, hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the first organization admin.")
    parser.add_argument("--organization", required=True, help="Organization display name.")
    parser.add_argument("--email", required=True, help="Admin email address.")
    parser.add_argument("--password", required=True, help="Initial admin password.")
    args = parser.parse_args()

    email = args.email.strip().lower()
    if "@" not in email:
        print("Admin email is invalid.", file=sys.stderr)
        return 2

    try:
        password_hash = hash_password(args.password)
    except PasswordHashError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            print("Admin user already exists.", file=sys.stderr)
            return 1

        organization = db.scalar(select(Organization).where(Organization.name == args.organization))
        if organization is None:
            organization = Organization(name=args.organization)
            db.add(organization)
            db.flush()

        user = User(
            organization_id=organization.id,
            email=email,
            role="admin",
            password_hash=password_hash,
        )
        db.add(user)
        db.commit()
        print(f"Created admin {user.email} for organization {organization.name}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
