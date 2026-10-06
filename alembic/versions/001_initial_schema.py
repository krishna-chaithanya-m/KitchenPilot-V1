"""Initial schema creation for KitchenPilot production database catalog.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-03 17:42:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. recipes table
    op.create_table(
        "recipes",
        sa.Column("recipe_id", sa.String(length=16), nullable=False),
        sa.Column("recipe_name", sa.String(length=512), nullable=False),
        sa.Column("name_local", sa.String(length=512), nullable=True),
        sa.Column("cuisine", sa.String(length=128), nullable=True),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("meal_type", sa.String(length=128), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("ingredients", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("prep_time_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cook_time_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_time_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("servings", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("diet_type", sa.String(length=128), nullable=True),
        sa.Column("vegetarian", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vegan", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("jain", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("satvik", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("contains", sa.String(length=256), nullable=True),
        sa.Column("source_id", sa.String(length=64), nullable=False, server_default="M001"),
        sa.Column("source_license", sa.String(length=64), nullable=False, server_default="CC BY 4.0"),
        sa.PrimaryKeyConstraint("recipe_id"),
    )
    op.create_index("ix_recipes_recipe_name", "recipes", ["recipe_name"])
    op.create_index("ix_recipes_cuisine", "recipes", ["cuisine"])
    op.create_index("ix_recipes_region", "recipes", ["region"])
    op.create_index("ix_recipes_meal_type", "recipes", ["meal_type"])
    op.create_index("ix_recipes_category", "recipes", ["category"])
    op.create_index("ix_recipes_diet_type", "recipes", ["diet_type"])
    op.create_index("ix_recipes_vegetarian", "recipes", ["vegetarian"])
    op.create_index("ix_recipes_vegan", "recipes", ["vegan"])
    op.create_index("ix_recipes_jain", "recipes", ["jain"])
    op.create_index("ix_recipes_satvik", "recipes", ["satvik"])

    # 2. ingredients table
    op.create_table(
        "ingredients",
        sa.Column("ingredient_id", sa.String(length=16), nullable=False),
        sa.Column("canonical_name", sa.String(length=256), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("ingredient_form", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("recipe_occurrence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_variant_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=256), nullable=False),
        sa.Column("mapping_status", sa.String(length=64), nullable=False, server_default="VALIDATED_AUTO"),
        sa.Column("vegetarian", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("vegan", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("allergen_flags", sa.JSON(), nullable=False),
        sa.Column("nutrition_reference", sa.String(length=256), nullable=True),
        sa.Column("default_unit", sa.String(length=32), nullable=False, server_default="g"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("ingredient_id"),
    )
    op.create_index("ix_ingredients_canonical_name", "ingredients", ["canonical_name"])
    op.create_index("ix_ingredients_category", "ingredients", ["category"])

    # 3. ingredient_aliases table
    op.create_table(
        "ingredient_aliases",
        sa.Column("alias_id", sa.String(length=16), nullable=False),
        sa.Column("canonical_ingredient_id", sa.String(length=16), nullable=False),
        sa.Column("alias", sa.String(length=256), nullable=False),
        sa.Column("normalized_alias", sa.String(length=256), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("review_status", sa.String(length=64), nullable=False, server_default="VALIDATED"),
        sa.ForeignKeyConstraint(["canonical_ingredient_id"], ["ingredients.ingredient_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("alias_id"),
    )
    op.create_index("ix_ingredient_aliases_canonical_id", "ingredient_aliases", ["canonical_ingredient_id"])
    op.create_index("ix_ingredient_aliases_alias", "ingredient_aliases", ["alias"])
    op.create_index("ix_ingredient_aliases_normalized_alias", "ingredient_aliases", ["normalized_alias"])
    op.create_index("ix_ingredient_aliases_review_status", "ingredient_aliases", ["review_status"])

    # 4. recipe_ingredients table
    op.create_table(
        "recipe_ingredients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipe_id", sa.String(length=16), nullable=False),
        sa.Column("original_ingredient", sa.Text(), nullable=False),
        sa.Column("quantity", sa.String(length=64), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("ingredient", sa.String(length=256), nullable=True),
        sa.Column("preparation", sa.String(length=256), nullable=True),
        sa.Column("ingredient_id", sa.String(length=16), nullable=True),
        sa.Column("canonical_ingredient", sa.String(length=256), nullable=True),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("ingredient_form", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("mapping_status", sa.String(length=64), nullable=False),
        sa.Column("mapping_source", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.ingredient_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.recipe_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recipe_ingredients_recipe_id", "recipe_ingredients", ["recipe_id"])
    op.create_index("ix_recipe_ingredients_ingredient_id", "recipe_ingredients", ["ingredient_id"])
    op.create_index("ix_recipe_ingredients_recipe_ing", "recipe_ingredients", ["recipe_id", "ingredient_id"])
    op.create_index("ix_recipe_ingredients_mapping_status", "recipe_ingredients", ["mapping_status"])

    # 5. recipe_nutrition table
    op.create_table(
        "recipe_nutrition",
        sa.Column("recipe_id", sa.String(length=16), nullable=False),
        sa.Column("recipe_name", sa.String(length=512), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_calories_kcal", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_protein_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_fat_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_carbs_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_fiber_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_sugar_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_sodium_mg", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("per_serving_calories_kcal", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("per_serving_protein_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("per_serving_fat_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("per_serving_carbs_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("per_serving_fiber_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("per_serving_sugar_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("per_serving_sodium_mg", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("nutrition_quality", sa.String(length=32), nullable=False, server_default="PARTIAL"),
        sa.Column("ingredient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calculated_ingredient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmapped_ingredient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("no_match_ingredient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("needs_review_ingredient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qualitative_quantity_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversion_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state_mismatch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.recipe_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("recipe_id"),
    )
    op.create_index("ix_recipe_nutrition_quality", "recipe_nutrition", ["nutrition_quality"])

    # 6. recipe_ingredient_nutrition table
    op.create_table(
        "recipe_ingredient_nutrition",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipe_id", sa.String(length=16), nullable=False),
        sa.Column("original_ingredient", sa.Text(), nullable=False),
        sa.Column("ingredient", sa.String(length=256), nullable=False),
        sa.Column("quantity", sa.String(length=64), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("preparation", sa.String(length=256), nullable=True),
        sa.Column("ingredient_id", sa.String(length=16), nullable=True),
        sa.Column("canonical_ingredient", sa.String(length=256), nullable=True),
        sa.Column("mapping_status", sa.String(length=64), nullable=False),
        sa.Column("curation_status", sa.String(length=64), nullable=True),
        sa.Column("cnf_food_code", sa.Float(), nullable=True),
        sa.Column("cnf_food_name", sa.String(length=512), nullable=True),
        sa.Column("parsed_quantity", sa.Float(), nullable=True),
        sa.Column("quantity_parse_status", sa.String(length=64), nullable=False),
        sa.Column("normalized_unit", sa.String(length=64), nullable=True),
        sa.Column("grams", sa.Float(), nullable=True),
        sa.Column("conversion_status", sa.String(length=64), nullable=False),
        sa.Column("state_status", sa.String(length=64), nullable=False),
        sa.Column("energy_kcal", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("protein_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("fat_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("carbs_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("fiber_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sugar_g", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sodium_mg", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mapping_quality", sa.String(length=64), nullable=False),
        sa.Column("nutrition_quality", sa.String(length=64), nullable=False),
        sa.Column("nutrition_source", sa.String(length=64), nullable=False),
        sa.Column("calculation_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.recipe_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recipe_ing_nutrition_recipe_id", "recipe_ingredient_nutrition", ["recipe_id"])
    op.create_index("ix_recipe_ing_nutrition_ing_id", "recipe_ingredient_nutrition", ["ingredient_id"])

    # 7. dataset_manifest_metadata table
    op.create_table(
        "dataset_manifest_metadata",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_name", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=256), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("import_status", sa.String(length=64), nullable=False, server_default="SUCCESS"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manifest_dataset_name", "dataset_manifest_metadata", ["dataset_name"], unique=True)


def downgrade() -> None:
    op.drop_table("dataset_manifest_metadata")
    op.drop_table("recipe_ingredient_nutrition")
    op.drop_table("recipe_nutrition")
    op.drop_table("recipe_ingredients")
    op.drop_table("ingredient_aliases")
    op.drop_table("ingredients")
    op.drop_table("recipes")
