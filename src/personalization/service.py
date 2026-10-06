"""Service layer managing user accounts, profiles, preferences, pantry, feedback, and history."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.personalization.features import UserPersonalizationContext
from src.personalization.models import (
    QualitativeFeedbackModel,
    RecommendationHistoryModel,
    UserFeedbackModel,
    UserModel,
    UserNutritionTargetModel,
    UserPantryModel,
    UserPreferenceModel,
)
from src.personalization.schemas import (
    FeedbackRequest,
    FeedbackType,
    LoginRequest,
    NutritionTargetRequest,
    PantryItemCreateRequest,
    PantryStatus,
    QualitativeFeedbackRequest,
    RegisterRequest,
    UpdatePreferencesRequest,
)
from src.personalization.security import hash_password, verify_password

logger = logging.getLogger("kitchenpilot.personalization.service")

# Lazy-loaded singleton for canonical ingredient ontology
_ontology_instance = None


def get_cached_ontology():
    """Retrieve or lazily initialize the canonical ingredient ontology."""
    global _ontology_instance
    if _ontology_instance is None:
        try:
            from src.ingredients.ontology import IngredientOntology
            _ontology_instance = IngredientOntology.load()
        except Exception as exc:
            logger.warning("Could not load IngredientOntology in personalization service: %s", exc)
            _ontology_instance = False
    return _ontology_instance if _ontology_instance is not False else None


class PersonalizationService:
    """Core domain service for user personalization, pantry, and explicit feedback."""

    @staticmethod
    def register_user(db: Session, req: RegisterRequest) -> UserModel:
        """Register a new user account with hashed password and default preferences."""
        clean_email = req.email.strip().lower()

        # Check existing user
        existing = db.execute(select(UserModel).where(UserModel.email == clean_email)).scalar_one_or_none()
        if existing:
            raise ValueError("Email address already registered.")

        pw_hash = hash_password(req.password)
        now = datetime.now(timezone.utc)

        user = UserModel(
            email=clean_email,
            password_hash=pw_hash,
            display_name=req.display_name.strip() if req.display_name else None,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()

        # Initialize default empty preferences and nutrition targets
        prefs = UserPreferenceModel(
            user_id=user.id,
            vegetarian=False,
            vegan=False,
            jain=False,
            satvik=False,
            preferred_cuisines=[],
            preferred_regions=[],
            preferred_meal_types=[],
            preferred_categories=[],
            preferred_ingredients=[],
            disliked_ingredients=[],
            created_at=now,
            updated_at=now,
        )
        targets = UserNutritionTargetModel(
            user_id=user.id,
            created_at=now,
            updated_at=now,
        )
        db.add(prefs)
        db.add(targets)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate_user(db: Session, req: LoginRequest) -> Optional[UserModel]:
        """Authenticate user credentials and update last login timestamp."""
        clean_email = req.email.strip().lower()
        user = db.execute(select(UserModel).where(UserModel.email == clean_email)).scalar_one_or_none()
        if not user or not user.is_active:
            return None

        if not verify_password(req.password, user.password_hash):
            return None

        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[UserModel]:
        """Retrieve user by primary key."""
        return db.execute(select(UserModel).where(UserModel.id == user_id)).scalar_one_or_none()

    @staticmethod
    def get_user_preferences(db: Session, user_id: int) -> UserPreferenceModel:
        """Retrieve or create user preferences."""
        prefs = db.execute(select(UserPreferenceModel).where(UserPreferenceModel.user_id == user_id)).scalar_one_or_none()
        if not prefs:
            now = datetime.now(timezone.utc)
            prefs = UserPreferenceModel(
                user_id=user_id,
                created_at=now,
                updated_at=now,
            )
            db.add(prefs)
            db.commit()
            db.refresh(prefs)
        return prefs

    @staticmethod
    def update_user_preferences(db: Session, user_id: int, req: UpdatePreferencesRequest) -> UserPreferenceModel:
        """Update configurable user preferences."""
        prefs = PersonalizationService.get_user_preferences(db, user_id)
        now = datetime.now(timezone.utc)

        if req.vegetarian is not None:
            prefs.vegetarian = req.vegetarian
        if req.vegan is not None:
            prefs.vegan = req.vegan
        if req.jain is not None:
            prefs.jain = req.jain
        if req.satvik is not None:
            prefs.satvik = req.satvik
        if req.preferred_cuisines is not None:
            prefs.preferred_cuisines = [c.strip() for c in req.preferred_cuisines if c.strip()]
        if req.preferred_regions is not None:
            prefs.preferred_regions = [r.strip() for r in req.preferred_regions if r.strip()]
        if req.preferred_meal_types is not None:
            prefs.preferred_meal_types = [m.strip() for m in req.preferred_meal_types if m.strip()]
        if req.preferred_categories is not None:
            prefs.preferred_categories = [cat.strip() for cat in req.preferred_categories if cat.strip()]
        if req.preferred_ingredients is not None:
            prefs.preferred_ingredients = [i.strip() for i in req.preferred_ingredients if i.strip()]
        if req.disliked_ingredients is not None:
            prefs.disliked_ingredients = [d.strip() for d in req.disliked_ingredients if d.strip()]

        prefs.updated_at = now
        db.commit()
        db.refresh(prefs)
        return prefs

    @staticmethod
    def get_user_nutrition_targets(db: Session, user_id: int) -> UserNutritionTargetModel:
        """Retrieve or create user nutrition targets."""
        targets = db.execute(select(UserNutritionTargetModel).where(UserNutritionTargetModel.user_id == user_id)).scalar_one_or_none()
        if not targets:
            now = datetime.now(timezone.utc)
            targets = UserNutritionTargetModel(
                user_id=user_id,
                created_at=now,
                updated_at=now,
            )
            db.add(targets)
            db.commit()
            db.refresh(targets)
        return targets

    @staticmethod
    def update_user_nutrition_targets(db: Session, user_id: int, req: NutritionTargetRequest) -> UserNutritionTargetModel:
        """Update configurable user nutrition targets."""
        targets = PersonalizationService.get_user_nutrition_targets(db, user_id)
        now = datetime.now(timezone.utc)

        fields = [
            "target_calories", "min_calories", "max_calories",
            "target_protein", "min_protein", "max_protein",
            "target_carbs", "min_carbs", "max_carbs",
            "target_fat", "min_fat", "max_fat",
            "target_fiber", "min_fiber", "max_fiber",
        ]
        for field_name in fields:
            val = getattr(req, field_name)
            if val is not None:
                setattr(targets, field_name, val)

        targets.updated_at = now
        db.commit()
        db.refresh(targets)
        return targets

    @staticmethod
    def get_user_pantry(db: Session, user_id: int) -> List[UserPantryModel]:
        """Retrieve all pantry items for a given user ordered by ingredient name."""
        return list(
            db.execute(
                select(UserPantryModel)
                .where(UserPantryModel.user_id == user_id)
                .order_by(UserPantryModel.ingredient_name.asc())
            ).scalars().all()
        )

    @staticmethod
    def add_or_update_pantry_item(db: Session, user_id: int, req: PantryItemCreateRequest) -> UserPantryModel:
        """Upsert a pantry item, resolving against canonical ingredient ontology if possible."""
        raw_name = req.ingredient_name.strip()
        ontology = get_cached_ontology()

        resolved_id = None
        display_name = raw_name
        if ontology:
            res = ontology.resolve(raw_name)
            if res and res.is_resolved:
                resolved_id = res.canonical_ingredient.ingredient_id
                display_name = res.canonical_ingredient.display_name

        now = datetime.now(timezone.utc)
        existing = db.execute(
            select(UserPantryModel)
            .where(UserPantryModel.user_id == user_id, func.lower(UserPantryModel.ingredient_name) == raw_name.lower())
        ).scalar_one_or_none()

        if existing:
            existing.ingredient_id = resolved_id or existing.ingredient_id
            existing.display_name = display_name
            existing.quantity = req.quantity
            existing.unit = req.unit
            existing.status = req.status.value
            existing.updated_at = now
            item = existing
        else:
            item = UserPantryModel(
                user_id=user_id,
                ingredient_id=resolved_id,
                ingredient_name=raw_name,
                display_name=display_name,
                quantity=req.quantity,
                unit=req.unit,
                status=req.status.value,
                created_at=now,
                updated_at=now,
            )
            db.add(item)

        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def remove_pantry_item(db: Session, user_id: int, item_id: int) -> bool:
        """Remove a pantry item owned by the user."""
        res = db.execute(
            delete(UserPantryModel).where(UserPantryModel.user_id == user_id, UserPantryModel.id == item_id)
        )
        db.commit()
        return res.rowcount > 0

    @staticmethod
    def record_feedback(db: Session, user_id: int, req: FeedbackRequest) -> UserFeedbackModel:
        """Upsert user feedback for a recipe (LIKE, DISLIKE, SAVE, COOKED, HIDE)."""
        now = datetime.now(timezone.utc)
        rid = req.recipe_id.strip()

        # Check existing feedback for this user, recipe, and feedback_type
        existing = db.execute(
            select(UserFeedbackModel).where(
                UserFeedbackModel.user_id == user_id,
                UserFeedbackModel.recipe_id == rid,
                UserFeedbackModel.feedback_type == req.feedback_type.value,
            )
        ).scalar_one_or_none()

        session_id = req.session_id.strip() if req.session_id else None

        if existing:
            existing.rating = req.rating
            existing.notes = req.notes
            existing.updated_at = now
            if session_id:
                existing.session_id = session_id
            fb = existing
        else:
            fb = UserFeedbackModel(
                user_id=user_id,
                recipe_id=rid,
                feedback_type=req.feedback_type.value,
                session_id=session_id,
                rating=req.rating,
                notes=req.notes,
                created_at=now,
                updated_at=now,
            )
            db.add(fb)

        db.commit()
        db.refresh(fb)
        return fb

    @staticmethod
    def get_user_feedback(
        db: Session,
        user_id: int,
        feedback_type: Optional[str] = None,
    ) -> List[UserFeedbackModel]:
        """Retrieve feedback items for user, optionally filtered by feedback_type."""
        query = select(UserFeedbackModel).where(UserFeedbackModel.user_id == user_id)
        if feedback_type:
            query = query.where(UserFeedbackModel.feedback_type == feedback_type.upper().strip())
        query = query.order_by(UserFeedbackModel.created_at.desc())
        return list(db.execute(query).scalars().all())

    @staticmethod
    def record_qualitative_feedback(
        db: Session,
        user_id: int,
        req: QualitativeFeedbackRequest,
    ) -> QualitativeFeedbackModel:
        """Record lightweight qualitative feedback from pilot participants."""
        now = datetime.now(timezone.utc)
        rid = req.recipe_id.strip() if req.recipe_id else None
        session_id = req.session_id.strip() if req.session_id else None
        comments = req.comments.strip() if req.comments else None

        item = QualitativeFeedbackModel(
            user_id=user_id,
            recipe_id=rid,
            session_id=session_id,
            issue_type=req.issue_type.value,
            comments=comments,
            created_at=now,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def get_qualitative_feedback(
        db: Session,
        user_id: Optional[int] = None,
        recipe_id: Optional[str] = None,
        issue_type: Optional[str] = None,
    ) -> List[QualitativeFeedbackModel]:
        """Retrieve qualitative feedback items, optionally filtered by user, recipe, or issue_type."""
        query = select(QualitativeFeedbackModel)
        if user_id is not None:
            query = query.where(QualitativeFeedbackModel.user_id == user_id)
        if recipe_id is not None:
            query = query.where(QualitativeFeedbackModel.recipe_id == recipe_id.strip())
        if issue_type is not None:
            query = query.where(QualitativeFeedbackModel.issue_type == issue_type.strip())
        query = query.order_by(QualitativeFeedbackModel.created_at.desc())
        return list(db.execute(query).scalars().all())

    @staticmethod
    def get_user_history(
        db: Session,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[int, List[RecommendationHistoryModel]]:
        """Retrieve paginated recommendation events for an authenticated user."""
        count_q = select(func.count(RecommendationHistoryModel.id)).where(RecommendationHistoryModel.user_id == user_id)
        total = db.execute(count_q).scalar_one()

        items_q = (
            select(RecommendationHistoryModel)
            .where(RecommendationHistoryModel.user_id == user_id)
            .order_by(RecommendationHistoryModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(db.execute(items_q).scalars().all())
        return total, items

    @staticmethod
    def get_user_context(db: Session, user_id: int) -> UserPersonalizationContext:
        """Compile a complete UserPersonalizationContext for recommendation reranking."""
        prefs = PersonalizationService.get_user_preferences(db, user_id)
        targets = PersonalizationService.get_user_nutrition_targets(db, user_id)
        pantry = PersonalizationService.get_user_pantry(db, user_id)
        feedback = PersonalizationService.get_user_feedback(db, user_id)

        # Recent history recipe IDs (last 30 events)
        recent_history_q = (
            select(RecommendationHistoryModel.recipe_id)
            .where(RecommendationHistoryModel.user_id == user_id)
            .order_by(RecommendationHistoryModel.created_at.desc())
            .limit(30)
        )
        recent_rec_ids = set(db.execute(recent_history_q).scalars().all())

        # Partition feedback by type
        liked = {f.recipe_id for f in feedback if f.feedback_type == FeedbackType.LIKE.value}
        saved = {f.recipe_id for f in feedback if f.feedback_type == FeedbackType.SAVE.value}
        cooked = {f.recipe_id for f in feedback if f.feedback_type == FeedbackType.COOKED.value}
        disliked = {f.recipe_id for f in feedback if f.feedback_type == FeedbackType.DISLIKE.value}
        hidden = {f.recipe_id for f in feedback if f.feedback_type == FeedbackType.HIDE.value}

        # Available pantry items (in stock or low)
        avail_pantry_ids = {p.ingredient_id for p in pantry if p.ingredient_id and p.status != PantryStatus.OUT_OF_STOCK.value}
        avail_pantry_names = {p.ingredient_name.strip().lower() for p in pantry if p.status != PantryStatus.OUT_OF_STOCK.value}

        return UserPersonalizationContext(
            user_id=user_id,
            vegetarian=prefs.vegetarian,
            vegan=prefs.vegan,
            jain=prefs.jain,
            satvik=prefs.satvik,
            preferred_cuisines=set(prefs.preferred_cuisines or []),
            preferred_regions=set(prefs.preferred_regions or []),
            preferred_meal_types=set(prefs.preferred_meal_types or []),
            preferred_categories=set(prefs.preferred_categories or []),
            preferred_ingredients=set(prefs.preferred_ingredients or []),
            disliked_ingredients=set(prefs.disliked_ingredients or []),
            pantry_ingredient_ids=avail_pantry_ids,
            pantry_ingredient_names=avail_pantry_names,
            liked_recipe_ids=liked,
            saved_recipe_ids=saved,
            cooked_recipe_ids=cooked,
            disliked_recipe_ids=disliked,
            hidden_recipe_ids=hidden,
            recent_recommended_recipe_ids=recent_rec_ids,
            calorie_target=targets.target_calories,
            min_calories=targets.min_calories,
            max_calories=targets.max_calories,
            protein_target=targets.target_protein,
            min_protein=targets.min_protein,
            max_protein=targets.max_protein,
        )

    @staticmethod
    def delete_user_data(db: Session, user_id: int, delete_account: bool = False) -> Dict[str, Any]:
        """Securely purge user-owned data (pantry, feedback, history, preferences, targets, account).

        Preserves shared recipe catalog and prevents cross-user modification.
        """
        pantry_del = db.execute(delete(UserPantryModel).where(UserPantryModel.user_id == user_id)).rowcount
        fb_del = db.execute(delete(UserFeedbackModel).where(UserFeedbackModel.user_id == user_id)).rowcount
        hist_del = db.execute(delete(RecommendationHistoryModel).where(RecommendationHistoryModel.user_id == user_id)).rowcount
        pref_del = db.execute(delete(UserPreferenceModel).where(UserPreferenceModel.user_id == user_id)).rowcount
        target_del = db.execute(delete(UserNutritionTargetModel).where(UserNutritionTargetModel.user_id == user_id)).rowcount
        qual_del = db.execute(delete(QualitativeFeedbackModel).where(QualitativeFeedbackModel.user_id == user_id)).rowcount

        account_deleted = False
        if delete_account:
            user_del = db.execute(delete(UserModel).where(UserModel.id == user_id)).rowcount
            account_deleted = (user_del > 0)
        else:
            # Recreate clean empty preferences and targets if retaining account
            now = datetime.now(timezone.utc)
            db.add(UserPreferenceModel(user_id=user_id, created_at=now, updated_at=now))
            db.add(UserNutritionTargetModel(user_id=user_id, created_at=now, updated_at=now))

        db.commit()
        return {
            "status": "purged",
            "user_id": user_id,
            "account_deleted": account_deleted,
            "purged_records": {
                "pantry_items": pantry_del,
                "feedback_events": fb_del,
                "history_events": hist_del,
                "preferences": pref_del,
                "nutrition_targets": target_del,
                "qualitative_feedback": qual_del,
            },
        }

