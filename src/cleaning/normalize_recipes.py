import re
import pandas as pd
from pathlib import Path


RAW_FILE = Path("data/raw/recipes/indian_recipes_raw.csv")
OUTPUT_FILE = Path("data/processed/recipes.csv")

CLEANING_PATTERNS = [
    r'\s+(?:Using|In|Made Using|Made with)\s+(?:Preethi|Preeti)\s+Electric\s+Pressure\s+Cooker\b',
    r'\s+-\s+Kids\s+Recipes\s+Made\s+With\s+Del\s+Monte\b',
    r'\s+(?:Using|In|Made Using)\s+Electric\s+Pressure\s+Cooker\b',
]

_TITLE_CLEANING_REGEX = re.compile(
    "|".join(f"(?:{p})" for p in CLEANING_PATTERNS),
    flags=re.IGNORECASE,
)


def clean_text(value):
    """Convert missing values to empty strings and normalize whitespace."""
    if pd.isna(value):
        return ""

    return " ".join(str(value).split())


def clean_recipe_title(value):
    """Normalize recipe title by removing commercial sponsor and appliance clauses.

    Preserves legitimate culinary vessels (Kadai, Tawa, Handi, Matka), ingredients
    (Pigeon Peas), and culinary techniques (Pressure Cooker Cake).
    """
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    if _TITLE_CLEANING_REGEX.search(cleaned):
        cleaned = _TITLE_CLEANING_REGEX.sub("", cleaned).strip()
        cleaned = re.sub(r"\s+-\s*$", "", cleaned).strip()
        return " ".join(cleaned.split())
    return cleaned


def normalize_diet(diet):
    """Convert dataset diet labels into standardized flags."""
    diet = clean_text(diet).lower()

    is_non_veg = (
        "non" in diet
        or "eggetarian" in diet
        or "meat" in diet
        or "fish" in diet
        or "chicken" in diet
        or "seafood" in diet
    )
    is_vegan = "vegan" in diet
    is_satvik = (
        "sattvic" in diet or "satvik" in diet or "no onion no garlic" in diet
    )
    is_veg = not is_non_veg and (
        "vegetarian" in diet or is_vegan or is_satvik
    )

    return {
        "vegetarian": is_veg,
        "vegan": is_vegan and not is_non_veg,
        "jain": False,
        "satvik": is_satvik and not is_non_veg,
    }


def normalize_recipe(row):
    diet_flags = normalize_diet(row["Diet"])

    return {
        "recipe_id": f"R{int(row['Srno']):05d}",
        "recipe_name": clean_recipe_title(row["TranslatedRecipeName"]),
        "name_local": clean_recipe_title(row["RecipeName"]),
        "cuisine": clean_text(row["Cuisine"]),
        "region": "",
        "meal_type": clean_text(row["Course"]),
        "category": clean_text(row["Course"]),
        "ingredients": clean_text(row["TranslatedIngredients"]),
        "instructions": clean_text(row["TranslatedInstructions"]),
        "prep_time_min": int(row["PrepTimeInMins"]),
        "cook_time_min": int(row["CookTimeInMins"]),
        "total_time_min": int(row["TotalTimeInMins"]),
        "servings": int(row["Servings"]),
        "diet_type": clean_text(row["Diet"]),
        "vegetarian": diet_flags["vegetarian"],
        "vegan": diet_flags["vegan"],
        "jain": diet_flags["jain"],
        "satvik": diet_flags["satvik"],
        "contains": "",
        "calories_kcal": "",
        "protein_g": "",
        "carbs_g": "",
        "fat_g": "",
        "fiber_g": "",
        "source_id": "M001",
        "source_license": "CC BY 4.0",
    }


def main():

    if not RAW_FILE.exists():
        print(f"Dataset not found: {RAW_FILE}")
        return

    print("Loading raw recipe dataset...")

    df = pd.read_csv(RAW_FILE)

    print(f"Loaded {len(df)} recipes.")

    normalized_records = []

    for _, row in df.iterrows():
        normalized_records.append(normalize_recipe(row))

    normalized_df = pd.DataFrame(normalized_records)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    normalized_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    print()
    print("Normalization complete.")
    print(f"Recipes processed: {len(normalized_df)}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
