"""Declarative base shared by every ORM model so they register on one
MetaData (needed for relationships, migrations, and create_all)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

