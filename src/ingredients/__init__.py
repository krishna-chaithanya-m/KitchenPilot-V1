"""KitchenPilot Ingredient Intelligence and Ontology package."""

from src.ingredients.models import (
    CanonicalIngredient,
    IngredientAlias,
    ParsedIngredientItem,
    ResolutionResult,
)
from src.ingredients.normalizer import (
    normalize_ingredient_phrase,
    parse_raw_ingredient_line,
)
from src.ingredients.aliases import (
    AliasRegistry,
    compile_ingredient_aliases,
)
from src.ingredients.ontology import (
    IngredientOntology,
)
from src.ingredients.validator import (
    OntologyValidationReport,
    validate_ontology,
)

__all__ = [
    "CanonicalIngredient",
    "IngredientAlias",
    "ParsedIngredientItem",
    "ResolutionResult",
    "normalize_ingredient_phrase",
    "parse_raw_ingredient_line",
    "AliasRegistry",
    "compile_ingredient_aliases",
    "IngredientOntology",
    "OntologyValidationReport",
    "validate_ontology",
]
