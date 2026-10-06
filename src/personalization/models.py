"""SQLAlchemy 2.x ORM models representing users, preferences, pantry, feedback, and history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class UserModel(Base):
    """User account entity for authentication and profile management."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    preferences: Mapped[Optional[UserPreferenceModel]] = relationship(
        "UserPreferenceModel", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    nutrition_targets: Mapped[Optional[UserNutritionTargetModel]] = relationship(
        "UserNutritionTargetModel", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    pantry_items: Mapped[List[UserPantryModel]] = relationship(
        "UserPantryModel", back_populates="user", cascade="all, delete-orphan"
    )
    feedback_items: Mapped[List[UserFeedbackModel]] = relationship(
        "UserFeedbackModel", back_populates="user", cascade="all, delete-orphan"
    )
    recommendation_history: Mapped[List[RecommendationHistoryModel]] = relationship(
        "RecommendationHistoryModel", back_populates="user", cascade="all, delete-orphan"
    )
    qualitative_feedback: Mapped[List[QualitativeFeedbackModel]] = relationship(
        "QualitativeFeedbackModel", back_populates="user", cascade="all, delete-orphan"
    )


class UserPreferenceModel(Base):
    """Persistent user dietary, cuisine, and food preferences."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    vegetarian: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vegan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    jain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    satvik: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferred_cuisines: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    preferred_regions: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    preferred_meal_types: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    preferred_categories: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    preferred_ingredients: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    disliked_ingredients: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped[UserModel] = relationship("UserModel", back_populates="preferences")


class UserNutritionTargetModel(Base):
    """User-configured daily or per-meal nutrition targets and boundary limits."""

    __tablename__ = "user_nutrition_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    target_calories: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_calories: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_calories: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_fat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_fat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_fat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_fiber: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_fiber: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_fiber: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped[UserModel] = relationship("UserModel", back_populates="nutrition_targets")


class UserPantryModel(Base):
    """Persistent user pantry items mapped to canonical ontology where applicable."""

    __tablename__ = "user_pantry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("ingredients.ingredient_id", ondelete="SET NULL"), nullable=True, index=True
    )
    ingredient_name: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="IN_STOCK")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped[UserModel] = relationship("UserModel", back_populates="pantry_items")

    __table_args__ = (
        UniqueConstraint("user_id", "ingredient_name", name="uq_user_pantry_user_ingredient"),
    )


class UserFeedbackModel(Base):
    """Explicit recipe interaction feedback (LIKE, DISLIKE, SAVE, COOKED, HIDE)."""

    __tablename__ = "user_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipe_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("recipes.recipe_id", ondelete="CASCADE"), nullable=False, index=True
    )
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped[UserModel] = relationship("UserModel", back_populates="feedback_items")

    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", "feedback_type", name="uq_user_recipe_feedback"),
        Index("ix_user_feedback_user_recipe", "user_id", "recipe_id"),
    )


class RecommendationHistoryModel(Base):
    """Recommendation event audit logging for reproducible analysis and future training data."""

    __tablename__ = "recommendation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recipe_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("recipes.recipe_id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    ranking_method: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    personalization_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    base_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    personalization_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    context_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    user: Mapped[Optional[UserModel]] = relationship("UserModel", back_populates="recommendation_history")


class QualitativeFeedbackModel(Base):
    """Lightweight qualitative UX feedback from real pilot participants.

    Kept strictly separated from ML training interactions and relevance labels.
    """

    __tablename__ = "qualitative_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipe_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("recipes.recipe_id", ondelete="CASCADE"), nullable=True, index=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    user: Mapped[UserModel] = relationship("UserModel", back_populates="qualitative_feedback")
