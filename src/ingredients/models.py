"""Domain data models for Canonical Ingredient Ontology and Aliases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class CanonicalIngredient:
    """Rich domain entity representing a validated canonical ingredient."""

    ingredient_id: str
    canonical_name: str
    display_name: str
    ingredient_form: str = "default"
    category: str = "other"
    vegetarian: bool = True
    vegan: bool = True
    allergen_flags: List[str] = field(default_factory=list)
    nutrition_reference: Optional[str] = None
    default_unit: str = "g"
    active: bool = True
    aliases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ingredient_id": self.ingredient_id,
            "canonical_name": self.canonical_name,
            "display_name": self.display_name,
            "ingredient_form": self.ingredient_form,
            "category": self.category,
            "vegetarian": self.vegetarian,
            "vegan": self.vegan,
            "allergen_flags": self.allergen_flags,
            "nutrition_reference": self.nutrition_reference,
            "default_unit": self.default_unit,
            "active": self.active,
            "aliases": self.aliases,
        }


@dataclass
class IngredientAlias:
    """Mapping entry linking a variant phrase to a canonical ingredient."""

    alias_id: str
    canonical_ingredient_id: str
    alias: str
    normalized_alias: str
    source: str
    confidence: float = 1.0
    review_status: str = "VALIDATED"  # 'AUTO', 'VALIDATED', 'REVIEW_REQUIRED', 'REJECTED'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alias_id": self.alias_id,
            "canonical_ingredient_id": self.canonical_ingredient_id,
            "alias": self.alias,
            "normalized_alias": self.normalized_alias,
            "source": self.source,
            "confidence": self.confidence,
            "review_status": self.review_status,
        }


@dataclass
class ParsedIngredientItem:
    """Result of parsing an ingredient line preserving quantity, unit, and preparation."""

    original_text: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    ingredient: str = ""
    preparation_state: Optional[str] = None
    canonical_ingredient_id: Optional[str] = None
    mapping_status: str = "UNMAPPED"  # 'MAPPED_CANONICAL', 'MAPPED_ALIAS', 'REVIEW_REQUIRED', 'UNMAPPED'
    normalization_trace: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_text": self.original_text,
            "quantity": self.quantity,
            "unit": self.unit,
            "ingredient": self.ingredient,
            "preparation_state": self.preparation_state,
            "canonical_ingredient_id": self.canonical_ingredient_id,
            "mapping_status": self.mapping_status,
            "normalization_trace": self.normalization_trace,
        }


@dataclass
class ResolutionResult:
    """Outcome of resolving an ingredient query against the ontology."""

    canonical_ingredient: Optional[CanonicalIngredient] = None
    matched_alias: Optional[IngredientAlias] = None
    confidence: float = 0.0
    match_method: str = "NONE"  # 'EXACT_CANONICAL', 'EXACT_ALIAS', 'NORMALIZED_ALIAS', 'NORMALIZED_TEXT', 'NONE'
    trace: List[str] = field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        return self.canonical_ingredient is not None
