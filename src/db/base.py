"""Declarative base class for SQLAlchemy 2.x ORM models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarative class for all KitchenPilot relational models."""
    pass
