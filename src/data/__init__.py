"""KitchenPilot Production Data Architecture module."""

from src.data.schemas import (
    RecipeSchema,
    CanonicalIngredientSchema,
    RecipeIngredientLinkedSchema,
    RecipeNutritionSchema,
    RecipeIngredientNutritionSchema,
    IngredientAliasSchema,
)
from src.data.contracts import (
    ValidationResult,
    validate_recipe_dataset,
    validate_ingredient_dataset,
    validate_recipe_ingredient_links,
    validate_recipe_nutrition_dataset,
    validate_recipe_ingredient_nutrition_dataset,
    validate_ingredient_aliases_dataset,
    validate_cross_dataset_integrity,
)

__all__ = [
    "RecipeSchema",
    "CanonicalIngredientSchema",
    "RecipeIngredientLinkedSchema",
    "RecipeNutritionSchema",
    "RecipeIngredientNutritionSchema",
    "IngredientAliasSchema",
    "ValidationResult",
    "validate_recipe_dataset",
    "validate_ingredient_dataset",
    "validate_recipe_ingredient_links",
    "validate_recipe_nutrition_dataset",
    "validate_recipe_ingredient_nutrition_dataset",
    "validate_ingredient_aliases_dataset",
    "validate_cross_dataset_integrity",
]
