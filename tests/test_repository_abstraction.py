"""Tests for repository abstraction, factory, and CSV/Postgres contracts."""

import pytest
from src.data.repository import BaseRecipeStore, PostgresRecipeStore
from src.api.dependencies import RecipeStore, create_recipe_store, get_recipe_store
from src.db.config import DATA_BACKEND


def _register_sqlite_regexp_replace(engine):
    """Register custom regexp_replace function on a specific SQLite test engine."""
    from sqlalchemy import event
    import re

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, connection_record):
        if hasattr(dbapi_connection, "create_function"):
            def _regexp_replace(text, pattern, replacement, flags=""):
                if text is None:
                    return None
                return re.sub(pattern, replacement, text)

            dbapi_connection.create_function(
                "regexp_replace", 3, lambda t, p, r: _regexp_replace(t, p, r)
            )
            dbapi_connection.create_function("regexp_replace", 4, _regexp_replace)

    return engine



def test_recipe_store_inherits_base_recipe_store():
    """Verify RecipeStore conforms to BaseRecipeStore interface."""
    assert issubclass(RecipeStore, BaseRecipeStore)
    assert issubclass(PostgresRecipeStore, BaseRecipeStore)


def test_factory_creates_csv_store_by_default(monkeypatch):
    """Verify create_recipe_store defaults to RecipeStore (CSV backend)."""
    monkeypatch.setenv("DATA_BACKEND", "csv")
    store = create_recipe_store()
    assert isinstance(store, RecipeStore)
    assert not isinstance(store, PostgresRecipeStore)


def test_factory_creates_postgres_store_when_configured(monkeypatch):
    """Verify create_recipe_store creates PostgresRecipeStore when DATA_BACKEND=postgres."""
    monkeypatch.setenv("DATA_BACKEND", "postgres")
    store = create_recipe_store()
    assert isinstance(store, PostgresRecipeStore)


def test_csv_store_implements_required_methods():
    """Verify CSV RecipeStore implements all abstract methods on BaseRecipeStore."""
    store = RecipeStore()
    assert hasattr(store, "exists")
    assert hasattr(store, "list_recipes")
    assert hasattr(store, "get_recipe")
    assert hasattr(store, "get_nutrition")
    assert hasattr(store, "get_recipe_ingredients")

    # Quick smoke test of CSV backend
    recipes, total, total_pages = store.list_recipes(page=1, page_size=5)
    assert len(recipes) == 5
    assert total == len(store.recipes_df)
    assert total < 6871
    assert all(
        store.recipes_df["cuisine"].apply(
            __import__("src.data.cuisine_policy", fromlist=["is_indian_cuisine"]).is_indian_cuisine
        )
    )
    first_id = recipes[0].recipe_id

    recipe = store.get_recipe(first_id)
    assert recipe is not None
    assert recipe.recipe_id == first_id

    nutrition = store.get_nutrition(first_id)
    assert nutrition is not None
    assert nutrition.recipe_id == first_id


def test_postgres_store_list_recipes_sql_pushdown(monkeypatch):
    """Verify PostgresRecipeStore.list_recipes pushes Indian allow-list, counts, and pagination to SQL."""
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.db.base import Base
    from src.db.models import RecipeModel
    import src.data.repository as repo_mod

    engine = _register_sqlite_regexp_replace(create_engine("sqlite:///:memory:"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(RecipeModel(
            recipe_id="R_IND_1", recipe_name="Dosa", cuisine="South Indian Recipes",
            region="South India", meal_type="Breakfast", category="Main Course",
            prep_time_min=10, cook_time_min=10, total_time_min=20, servings=2,
            vegetarian=True, vegan=True, jain=True, satvik=True,
        ))
        session.add(RecipeModel(
            recipe_id="R_IND_2", recipe_name="Biryani", cuisine="Hyderabadi",
            region="South India", meal_type="Dinner", category="Main Course",
            prep_time_min=20, cook_time_min=30, total_time_min=50, servings=4,
            vegetarian=False, vegan=False, jain=False, satvik=False,
        ))
        session.add(RecipeModel(
            recipe_id="R_IND_3", recipe_name="Dhokla", cuisine="Gujarati Recipes",
            region="West India", meal_type="Snack", category="Side Dish",
            prep_time_min=10, cook_time_min=20, total_time_min=30, servings=4,
            vegetarian=True, vegan=False, jain=True, satvik=False,
        ))
        session.add(RecipeModel(
            recipe_id="R_NON_1", recipe_name="Tacos", cuisine="Mexican",
            region="Central America", meal_type="Dinner", category="Main Course",
            prep_time_min=10, cook_time_min=10, total_time_min=20, servings=2,
            vegetarian=False, vegan=False, jain=False, satvik=False,
        ))
        session.add(RecipeModel(
            recipe_id="R_NON_2", recipe_name="Pasta", cuisine="Italian Recipes",
            region="Europe", meal_type="Dinner", category="Main Course",
            prep_time_min=10, cook_time_min=15, total_time_min=25, servings=2,
            vegetarian=True, vegan=False, jain=False, satvik=False,
        ))
        session.commit()

    @contextmanager
    def mock_db_session():
        with Session(engine) as s:
            yield s

    monkeypatch.setattr(repo_mod, "get_db_session", mock_db_session)
    store = PostgresRecipeStore()

    # Page 1, page_size 2: Should only count and return Indian recipes (3 total, 2 on page 1)
    page1, total, total_pages = store.list_recipes(page=1, page_size=2)
    assert total == 3
    assert total_pages == 2
    assert len(page1) == 2
    for r in page1:
        assert r.recipe_id in ("R_IND_1", "R_IND_2", "R_IND_3")

    # Page 2: should return the 3rd Indian recipe
    page2, total2, _ = store.list_recipes(page=2, page_size=2)
    assert total2 == 3
    assert len(page2) == 1

    # Page boundary: page beyond total pages returns empty list with correct total/pages
    page_out_of_bounds, total_oob, pages_oob = store.list_recipes(page=99, page_size=2)
    assert total_oob == 3
    assert pages_oob == 2
    assert len(page_out_of_bounds) == 0

    # Vegetarian filter in SQL: should return only vegetarian Indian recipes
    veg_recipes, veg_total, _ = store.list_recipes(vegetarian=True)
    assert veg_total == 2
    assert {r.recipe_id for r in veg_recipes} == {"R_IND_1", "R_IND_3"}

    # Vegan filter in SQL
    vegan_recipes, vegan_total, _ = store.list_recipes(vegan=True)
    assert vegan_total == 1
    assert vegan_recipes[0].recipe_id == "R_IND_1"

    # Jain filter in SQL
    jain_recipes, jain_total, _ = store.list_recipes(jain=True)
    assert jain_total == 2
    assert {r.recipe_id for r in jain_recipes} == {"R_IND_1", "R_IND_3"}

    # Satvik filter in SQL
    satvik_recipes, satvik_total, _ = store.list_recipes(satvik=True)
    assert satvik_total == 1
    assert satvik_recipes[0].recipe_id == "R_IND_1"

    # Region, meal_type, category filters in SQL
    region_recs, reg_total, _ = store.list_recipes(region="South India")
    assert reg_total == 2
    assert {r.recipe_id for r in region_recs} == {"R_IND_1", "R_IND_2"}

    meal_recs, meal_total, _ = store.list_recipes(meal_type="Breakfast")
    assert meal_total == 1
    assert meal_recs[0].recipe_id == "R_IND_1"

    cat_recs, cat_total, _ = store.list_recipes(category="Side Dish")
    assert cat_total == 1
    assert cat_recs[0].recipe_id == "R_IND_3"

    # Unapproved cuisine filter in SQL: returns 0 total even if present in table
    non_ind_recs, non_ind_total, non_ind_pages = store.list_recipes(cuisine="Mexican")
    assert non_ind_total == 0
    assert non_ind_pages == 1
    assert len(non_ind_recs) == 0


def test_postgres_store_whitespace_and_case_consistency_with_cuisine_policy(monkeypatch):
    """Verify that PostgresRecipeStore SQL predicate matches is_indian_cuisine() across all whitespace/case variants."""
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.db.base import Base
    from src.db.models import RecipeModel
    from src.data.cuisine_policy import is_indian_cuisine
    import src.data.repository as repo_mod

    engine = _register_sqlite_regexp_replace(create_engine("sqlite:///:memory:"))
    Base.metadata.create_all(engine)

    test_recipes_data = [
        # Approved cuisines with various whitespace and casing
        ("R_WS_1", "Dosa", "  South   Indian   Recipes  "),
        ("R_WS_2", "Paneer Tikka", "NoRtH\t\tInDiAn  ReCiPeS"),
        ("R_WS_3", "Chole", "  PUNJABI  "),
        ("R_WS_4", "Fish Curry", "bengali   recipes\n"),
        # Invalid / missing / unapproved cuisines
        ("R_INV_1", "Blank 1", "   "),
        ("R_INV_2", "Blank 2", ""),
        ("R_INV_3", "Null Cuisine", None),
        ("R_INV_4", "Tacos", "  Mexican  "),
        ("R_INV_5", "Pasta", "Italian   Recipes"),
    ]

    with Session(engine) as session:
        for rid, name, c in test_recipes_data:
            session.add(RecipeModel(recipe_id=rid, recipe_name=name, cuisine=c))
        session.commit()

    @contextmanager
    def mock_db_session():
        with Session(engine) as s:
            yield s

    monkeypatch.setattr(repo_mod, "get_db_session", mock_db_session)
    store = PostgresRecipeStore()

    # 1. Unfiltered list_recipes: Must match is_indian_cuisine exactly for all test records
    recs, total, total_pages = store.list_recipes(page=1, page_size=20)
    returned_ids = {r.recipe_id for r in recs}

    expected_ids = {rid for rid, _, c in test_recipes_data if is_indian_cuisine(c)}
    rejected_ids = {rid for rid, _, c in test_recipes_data if not is_indian_cuisine(c)}

    assert expected_ids == {"R_WS_1", "R_WS_2", "R_WS_3", "R_WS_4"}
    assert rejected_ids == {"R_INV_1", "R_INV_2", "R_INV_3", "R_INV_4", "R_INV_5"}
    assert total == len(expected_ids)
    assert returned_ids == expected_ids
    assert returned_ids.isdisjoint(rejected_ids)

    # 2. Filtering by cuisine with whitespace/case variations
    # Normalized query should match recipe even if DB or query has repeated internal whitespace
    recs_south, tot_south, _ = store.list_recipes(cuisine="south indian recipes")
    assert tot_south == 1
    assert recs_south[0].recipe_id == "R_WS_1"

    recs_south_ws, tot_south_ws, _ = store.list_recipes(cuisine="   South   Indian    Recipes   ")
    assert tot_south_ws == 1
    assert recs_south_ws[0].recipe_id == "R_WS_1"

    recs_north, tot_north, _ = store.list_recipes(cuisine="north indian recipes")
    assert tot_north == 1
    assert recs_north[0].recipe_id == "R_WS_2"

    recs_punjabi, tot_punjabi, _ = store.list_recipes(cuisine="punjabi")
    assert tot_punjabi == 1
    assert recs_punjabi[0].recipe_id == "R_WS_3"

    # 3. Filtering by unapproved or whitespace-only cuisine returns 0 results
    recs_mex, tot_mex, _ = store.list_recipes(cuisine="  Mexican  ")
    assert tot_mex == 0
    assert len(recs_mex) == 0

    recs_blank, tot_blank, _ = store.list_recipes(cuisine="   ")
    assert tot_blank == 0
    assert len(recs_blank) == 0

    # 4. exists() and get_recipe() consistency
    for rid, _, c in test_recipes_data:
        should_exist = is_indian_cuisine(c)
        assert store.exists(rid) is should_exist
        detail = store.get_recipe(rid)
        assert (detail is not None) is should_exist


def test_csv_and_postgres_cuisine_whitespace_parity_regression(monkeypatch, tmp_path):
    """Regression test verifying 100% parity between CSV and PostgreSQL stores on whitespace, case, and policy consistency."""
    import pandas as pd
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.db.base import Base
    from src.db.models import RecipeModel, RecipeIngredientModel, RecipeNutritionModel
    from src.data.cuisine_policy import is_indian_cuisine
    import src.data.repository as repo_mod
    import src.api.dependencies as deps_mod

    # Diverse dataset covering mixed case, whitespace variants, missing values, unapproved labels
    test_data = [
        # Approved Indian cuisines with whitespace and casing variants
        {"recipe_id": "REC_WS_1", "recipe_name": "Dosa", "cuisine": "  South   Indian   Recipes  ", "ingredients": "rice, dal"},
        {"recipe_id": "REC_WS_2", "recipe_name": "Paneer Tikka", "cuisine": "NoRtH\t\tInDiAn  ReCiPeS", "ingredients": "paneer, spices"},
        {"recipe_id": "REC_WS_3", "recipe_name": "Chole", "cuisine": "  PUNJABI  ", "ingredients": "chana, onion"},
        {"recipe_id": "REC_WS_4", "recipe_name": "Fish Curry", "cuisine": "bengali   recipes\n", "ingredients": "fish, mustard"},
        {"recipe_id": "REC_WS_5", "recipe_name": "Hyderabadi Biryani", "cuisine": "\t hyderabadi \t", "ingredients": "rice, saffron"},
        # Invalid / missing / unapproved cuisines
        {"recipe_id": "REC_INV_1", "recipe_name": "Blank 1", "cuisine": "   ", "ingredients": "water"},
        {"recipe_id": "REC_INV_2", "recipe_name": "Blank 2", "cuisine": "", "ingredients": "salt"},
        {"recipe_id": "REC_INV_3", "recipe_name": "Null Cuisine", "cuisine": None, "ingredients": "pepper"},
        {"recipe_id": "REC_INV_4", "recipe_name": "Tacos", "cuisine": "  Mexican  ", "ingredients": "tortilla"},
        {"recipe_id": "REC_INV_5", "recipe_name": "Pasta", "cuisine": "Italian   Recipes", "ingredients": "pasta"},
        {"recipe_id": "REC_INV_6", "recipe_name": "Burger", "cuisine": "American", "ingredients": "patty"},
    ]

    # Setup SQLite database for PostgresRecipeStore
    engine = _register_sqlite_regexp_replace(create_engine("sqlite:///:memory:"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for item in test_data:
            session.add(RecipeModel(
                recipe_id=item["recipe_id"],
                recipe_name=item["recipe_name"],
                cuisine=item["cuisine"],
                ingredients=item["ingredients"],
                servings=2,
            ))
            session.add(RecipeNutritionModel(
                recipe_id=item["recipe_id"],
                recipe_name=item["recipe_name"],
                servings=2,
                nutrition_quality="HIGH",
            ))
            session.add(RecipeIngredientModel(
                recipe_id=item["recipe_id"],
                original_ingredient=item["ingredients"],
                mapping_status="VALIDATED",
                mapping_source="TEST",
            ))
        session.commit()

    @contextmanager
    def mock_db_session():
        with Session(engine) as s:
            yield s

    monkeypatch.setattr(repo_mod, "get_db_session", mock_db_session)

    # Setup CSV files for RecipeStore
    recipes_csv = tmp_path / "test_recipes.csv"
    nutrition_csv = tmp_path / "test_nutrition.csv"

    csv_rows = []
    nut_rows = []
    for item in test_data:
        csv_rows.append({
            "recipe_id": item["recipe_id"],
            "recipe_name": item["recipe_name"],
            "name_local": None,
            "cuisine": item["cuisine"],
            "region": "India",
            "meal_type": "Main",
            "category": "Main",
            "ingredients": item["ingredients"],
            "instructions": "Cook it",
            "prep_time_min": 10,
            "cook_time_min": 15,
            "total_time_min": 25,
            "servings": 2,
            "diet_type": "Vegetarian",
            "vegetarian": True,
            "vegan": False,
            "jain": False,
            "satvik": False,
            "contains": "",
        })
        nut_rows.append({
            "recipe_id": item["recipe_id"],
            "recipe_name": item["recipe_name"],
            "servings": 2,
            "per_serving_calories_kcal": 200,
            "per_serving_protein_g": 5,
            "per_serving_fat_g": 3,
            "per_serving_carbs_g": 30,
            "per_serving_fiber_g": 2,
            "per_serving_sugar_g": 1,
            "per_serving_sodium_mg": 100,
            "nutrition_quality": "HIGH",
            "total_calories_kcal": 400,
            "total_protein_g": 10,
            "total_fat_g": 6,
            "total_carbs_g": 60,
            "total_fiber_g": 4,
            "total_sugar_g": 2,
            "total_sodium_mg": 200,
        })

    pd.DataFrame(csv_rows).to_csv(recipes_csv, index=False)
    pd.DataFrame(nut_rows).to_csv(nutrition_csv, index=False)

    monkeypatch.setattr(deps_mod, "RECIPES_PATH", recipes_csv)
    monkeypatch.setattr(deps_mod, "RECIPE_NUTRITION_PATH", nutrition_csv)

    pg_store = PostgresRecipeStore()
    csv_store = RecipeStore()

    # 1. Unfiltered list_recipes parity: both must accept exactly the 5 approved Indian recipes
    pg_recs, pg_total, pg_pages = pg_store.list_recipes(page=1, page_size=10)
    csv_recs, csv_total, csv_pages = csv_store.list_recipes(page=1, page_size=10)

    expected_ids = {"REC_WS_1", "REC_WS_2", "REC_WS_3", "REC_WS_4", "REC_WS_5"}
    assert pg_total == csv_total == len(expected_ids)
    assert pg_pages == csv_pages == 1
    assert {r.recipe_id for r in pg_recs} == {r.recipe_id for r in csv_recs} == expected_ids

    # 2. Individual query parity for all records: exists, get_recipe, get_nutrition, get_recipe_ingredients
    for item in test_data:
        rid = item["recipe_id"]
        c = item["cuisine"]
        is_approved = is_indian_cuisine(c)

        # exists() parity
        assert pg_store.exists(rid) == csv_store.exists(rid) == is_approved

        # get_recipe() parity
        pg_rec = pg_store.get_recipe(rid)
        csv_rec = csv_store.get_recipe(rid)
        assert (pg_rec is not None) == (csv_rec is not None) == is_approved

        # get_nutrition() parity
        pg_nut = pg_store.get_nutrition(rid)
        csv_nut = csv_store.get_nutrition(rid)
        assert (pg_nut is not None) == (csv_nut is not None) == is_approved

        # get_recipe_ingredients() parity
        pg_ings = pg_store.get_recipe_ingredients(rid)
        csv_ings = csv_store.get_recipe_ingredients(rid)
        assert (len(pg_ings) > 0) == (len(csv_ings) > 0) == is_approved

    # 3. Filtering by cuisine with various whitespace and casing queries
    queries = [
        ("south indian recipes", "REC_WS_1"),
        ("   South   Indian   Recipes   ", "REC_WS_1"),
        ("north indian recipes", "REC_WS_2"),
        ("NoRtH\tInDiAn  ReCiPeS", "REC_WS_2"),
        ("punjabi", "REC_WS_3"),
        ("   PUNJABI   ", "REC_WS_3"),
        ("bengali recipes", "REC_WS_4"),
        ("  hyderabadi  ", "REC_WS_5"),
    ]
    for q_str, expected_id in queries:
        pg_filtered, pg_filt_tot, _ = pg_store.list_recipes(cuisine=q_str)
        csv_filtered, csv_filt_tot, _ = csv_store.list_recipes(cuisine=q_str)

        assert pg_filt_tot == csv_filt_tot == 1
        assert [r.recipe_id for r in pg_filtered] == [r.recipe_id for r in csv_filtered] == [expected_id]

    # 4. Reject unapproved, blank, or missing cuisines on both stores
    invalid_queries = [
        "Mexican",
        "  Mexican  ",
        "Italian Recipes",
        "American",
        "   ",
        "",
        "\t\n",
    ]
    for inv_q in invalid_queries:
        pg_inv, pg_inv_tot, _ = pg_store.list_recipes(cuisine=inv_q)
        csv_inv, csv_inv_tot, _ = csv_store.list_recipes(cuisine=inv_q)
        assert pg_inv_tot == csv_inv_tot == 0
        assert len(pg_inv) == len(csv_inv) == 0

    # 5. Pagination efficiency: SQL pagination with page_size=2
    p1, tot1, pages1 = pg_store.list_recipes(page=1, page_size=2)
    assert tot1 == 5
    assert pages1 == 3
    assert len(p1) == 2

    p2, tot2, pages2 = pg_store.list_recipes(page=2, page_size=2)
    assert tot2 == 5
    assert pages2 == 3
    assert len(p2) == 2

    p3, tot3, pages3 = pg_store.list_recipes(page=3, page_size=2)
    assert tot3 == 5
    assert pages3 == 3
    assert len(p3) == 1
