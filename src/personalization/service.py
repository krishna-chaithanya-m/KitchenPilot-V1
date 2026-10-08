"""Service layer managing user accounts, profiles, preferences, pantry, feedback, and history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.config import (
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES,
    ENVIRONMENT,
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    PILOT_INVITE_CODE,
    PILOT_MAX_USERS,
    PILOT_MODE,
    REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN,
)
from src.personalization.features import UserPersonalizationContext
from src.personalization.models import (
    EmailVerificationTokenModel,
    FederatedIdentityModel,
    PasswordResetTokenModel,
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
from src.personalization.security import (
    hash_password,
    hash_token,
    verify_google_id_token,
    verify_password,
)


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


def _normalize_utc(dt: datetime) -> datetime:
    """Ensure datetime is offset-aware in UTC (normalizes SQLite naive datetimes)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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

        if REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN and not user.is_verified:
            logger.warning("Authentication rejected: unverified user <%s>.", user.email)
            return None

        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def create_email_verification_token(db: Session, user_id: int) -> str:
        """Generate a cryptographically random verification token and store its SHA-256 hash.

        Invalidates previous unused verification tokens for the user.
        Returns the raw token string to be dispatched via email.
        """
        now = datetime.now(timezone.utc)
        # Invalidate prior unused verification tokens for this user
        db.execute(
            delete(EmailVerificationTokenModel).where(
                EmailVerificationTokenModel.user_id == user_id,
                EmailVerificationTokenModel.used_at.is_(None),
            )
        )

        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        expires_at = now + timedelta(minutes=EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES)

        token_record = EmailVerificationTokenModel(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=now,
            used_at=None,
        )
        db.add(token_record)
        db.commit()
        return raw_token

    @staticmethod
    def verify_email_token(db: Session, raw_token: str) -> UserModel:
        """Validate an email verification token and mark the user verified.

        Rejects invalid, expired, or already-used tokens.
        """
        if not raw_token or not isinstance(raw_token, str):
            raise ValueError("Invalid verification token.")

        token_hash = hash_token(raw_token)
        now = datetime.now(timezone.utc)

        token_record = db.execute(
            select(EmailVerificationTokenModel).where(
                EmailVerificationTokenModel.token_hash == token_hash
            )
        ).scalar_one_or_none()

        if not token_record or token_record.used_at is not None:
            raise ValueError("Invalid or already used verification token.")

        if now > _normalize_utc(token_record.expires_at):
            raise ValueError("Verification token has expired. Please request a new verification email.")


        user = db.get(UserModel, token_record.user_id)
        if not user or not user.is_active:
            raise ValueError("User account not found or is inactive.")

        user.is_verified = True
        user.updated_at = now
        token_record.used_at = now
        db.commit()
        db.refresh(user)
        logger.info("User <%s> email successfully verified.", user.email)
        return user

    @staticmethod
    def request_resend_verification(db: Session, email: str) -> Optional[Tuple[UserModel, str]]:
        """Prepare fresh verification token if user exists and is unverified.

        Anti-enumeration safe: Returns None if user not found or already verified,
        allowing the API route to emit a uniform success message without account leakage.
        """
        clean_email = email.strip().lower()
        user = db.execute(
            select(UserModel).where(UserModel.email == clean_email)
        ).scalar_one_or_none()

        if not user or not user.is_active or user.is_verified:
            return None

        raw_token = PersonalizationService.create_email_verification_token(db, user.id)
        return user, raw_token

    @staticmethod
    def request_password_reset(db: Session, email: str) -> Optional[Tuple[UserModel, str]]:
        """Generate a time-bounded password reset token if user exists.

        Anti-enumeration safe: Returns None if user not found or inactive,
        allowing caller to emit uniform success message without account leakage.
        Stores only the SHA-256 digest in the database.
        """
        clean_email = email.strip().lower()
        user = db.execute(
            select(UserModel).where(UserModel.email == clean_email)
        ).scalar_one_or_none()

        if not user or not user.is_active:
            return None

        now = datetime.now(timezone.utc)
        # Invalidate prior unused reset tokens for this user
        db.execute(
            delete(PasswordResetTokenModel).where(
                PasswordResetTokenModel.user_id == user.id,
                PasswordResetTokenModel.used_at.is_(None),
            )
        )

        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        expires_at = now + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)

        token_record = PasswordResetTokenModel(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=now,
            used_at=None,
        )
        db.add(token_record)
        db.commit()
        return user, raw_token

    @staticmethod
    def create_password_reset_token(db: Session, email: str) -> Optional[Tuple[UserModel, str]]:
        """Alias for request_password_reset."""
        return PersonalizationService.request_password_reset(db, email)

    @staticmethod
    def reset_password_with_token(db: Session, raw_token: str, new_password: str) -> UserModel:

        """Validate password reset token and update password using Argon2id.

        Rejects invalid, expired, or already-used tokens.
        Immediately revokes the reset token upon successful password update.
        """
        if not raw_token or not isinstance(raw_token, str):
            raise ValueError("Invalid password reset token.")

        token_hash = hash_token(raw_token)
        now = datetime.now(timezone.utc)

        token_record = db.execute(
            select(PasswordResetTokenModel).where(
                PasswordResetTokenModel.token_hash == token_hash
            )
        ).scalar_one_or_none()

        if not token_record or token_record.used_at is not None:
            raise ValueError("Invalid or already used password reset token.")

        if now > _normalize_utc(token_record.expires_at):
            raise ValueError("Password reset token has expired. Please request a new reset link.")


        user = db.get(UserModel, token_record.user_id)
        if not user or not user.is_active:
            raise ValueError("User account not found or is inactive.")

        # Update password hash using existing production Argon2id parameters
        user.password_hash = hash_password(new_password)
        user.updated_at = now
        token_record.used_at = now

        # Revoke any other unexpired reset tokens for this user
        db.execute(
            delete(PasswordResetTokenModel).where(
                PasswordResetTokenModel.user_id == user.id,
                PasswordResetTokenModel.id != token_record.id,
            )
        )

        db.commit()
        db.refresh(user)
        logger.info("Password successfully reset for user <%s>.", user.email)
        return user

    @staticmethod
    def authenticate_google_user(
        db: Session,
        id_token_str: str,
        invite_code: Optional[str] = None,
    ) -> Tuple[UserModel, bool]:
        """Authenticate or provision a user via Google OAuth/OIDC ID token.

        Features:
        A. Existing federated identity:
           If the Google subject (sub) is already linked, authenticates that user.
        B. Existing local account with matching verified email:
           Safely links the Google identity to the existing account.
           Preserves existing user ID, pantry, preferences, feedback, and history.
           Marks the user's email as verified.
        C. New Google user:
           Enforces pilot mode, capacity, and invite restrictions before provisioning.
           Creates a new user with verified email and default preferences/targets.
        D. Identity conflict rejection:
           Rejects attempts to link one Google identity to multiple users or a user to multiple Google identities.
           Safely handles race conditions via transaction rollback.

        Returns:
            Tuple[UserModel, bool]: (authenticated_user, is_newly_created)
        """
        payload = verify_google_id_token(id_token_str)
        sub = str(payload["sub"])
        email = payload["email"].strip().lower()
        now = datetime.now(timezone.utc)

        # A. Check if Google subject (sub) is already linked to an existing user
        fed = db.execute(
            select(FederatedIdentityModel).where(
                FederatedIdentityModel.provider == "google",
                FederatedIdentityModel.provider_user_id == sub,
            )
        ).scalar_one_or_none()

        if fed:
            user = db.execute(select(UserModel).where(UserModel.id == fed.user_id)).scalar_one_or_none()
            if not user or not user.is_active:
                raise ValueError("User account is inactive or disabled.")

            # Check if token email conflicts with another user account
            if user.email != email:
                conflict_user = db.execute(select(UserModel).where(UserModel.email == email)).scalar_one_or_none()
                if conflict_user and conflict_user.id != user.id:
                    raise ValueError("Identity conflict: Google identity already linked to a different account.")

            user.is_verified = True
            user.last_login_at = now
            db.commit()
            db.refresh(user)
            logger.info("Google authentication successful for existing linked user <%s>.", user.email)
            return user, False

        # B. Check if a local account exists with the same verified email
        existing_user = db.execute(select(UserModel).where(UserModel.email == email)).scalar_one_or_none()
        if existing_user:
            if not existing_user.is_active:
                raise ValueError("User account is inactive or disabled.")

            # Check if this user already has a DIFFERENT Google identity linked
            existing_user_fed = db.execute(
                select(FederatedIdentityModel).where(
                    FederatedIdentityModel.user_id == existing_user.id,
                    FederatedIdentityModel.provider == "google",
                )
            ).scalar_one_or_none()
            if existing_user_fed and existing_user_fed.provider_user_id != sub:
                raise ValueError("Identity conflict: User account is already linked to a different Google account.")

            # Create federated link to existing account
            new_fed = FederatedIdentityModel(
                user_id=existing_user.id,
                provider="google",
                provider_user_id=sub,
                email=email,
                created_at=now,
                updated_at=now,
            )
            db.add(new_fed)
            existing_user.is_verified = True
            existing_user.last_login_at = now
            existing_user.updated_at = now

            try:
                db.commit()
                db.refresh(existing_user)
                logger.info("Linked Google identity to existing user <%s> (id=%s).", existing_user.email, existing_user.id)
                return existing_user, False
            except IntegrityError:
                db.rollback()
                raise ValueError("Identity conflict during Google account linking.")

        # C. New Google user provisioning: Enforce pilot mode admission controls first
        from src.api.config import (
            ENVIRONMENT,
            PILOT_INVITE_CODE,
            PILOT_MAX_USERS,
            PILOT_MODE,
        )

        if ENVIRONMENT == "production" and not PILOT_MODE:
            raise PermissionError("Pilot onboarding is currently paused. Please check back later.")

        if PILOT_MODE:
            user_count = db.query(func.count(UserModel.id)).scalar() or 0
            if user_count >= PILOT_MAX_USERS:
                raise PermissionError(f"Controlled pilot cohort capacity reached ({PILOT_MAX_USERS} max users).")
            if PILOT_INVITE_CODE:
                if not invite_code or invite_code.strip() != PILOT_INVITE_CODE:
                    raise PermissionError("Invalid or missing pilot invite code.")

        # Provision new Google user
        random_secret = secrets.token_urlsafe(32)
        pw_hash = hash_password(random_secret)

        raw_name = payload.get("name") or payload.get("given_name")
        display_name = raw_name.strip()[:128] if raw_name and isinstance(raw_name, str) else None

        new_user = UserModel(
            email=email,
            password_hash=pw_hash,
            display_name=display_name,
            is_active=True,
            is_verified=True,
            auth_provider="google",
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )
        db.add(new_user)
        db.flush()

        # Initialize default user preferences and nutrition targets
        prefs = UserPreferenceModel(
            user_id=new_user.id,
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
            user_id=new_user.id,
            created_at=now,
            updated_at=now,
        )
        fed_record = FederatedIdentityModel(
            user_id=new_user.id,
            provider="google",
            provider_user_id=sub,
            email=email,
            created_at=now,
            updated_at=now,
        )
        db.add(prefs)
        db.add(targets)
        db.add(fed_record)

        try:
            db.commit()
            db.refresh(new_user)
            logger.info("Successfully provisioned new Google user <%s> (id=%s).", new_user.email, new_user.id)
            return new_user, True
        except IntegrityError:
            db.rollback()
            raise ValueError("Identity conflict or concurrent registration detected.")


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

