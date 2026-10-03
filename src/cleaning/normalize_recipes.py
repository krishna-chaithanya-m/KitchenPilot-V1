import pandas as pd
from pathlib import Path


RAW_FILE = Path("data/raw/recipes/indian_recipes_raw.csv")
OUTPUT_FILE = Path("data/processed/recipes.csv")


def clean_text(value):
    """Convert missing values to empty strings and normalize whitespace."""
    if pd.isna(value):
        return ""

    return " ".join(str(value).split())


def normalize_diet(diet):
    """Convert dataset diet labels into standardized flags."""
    diet = clean_text(diet).lower()

    return {
        "vegetarian": "vegetarian" in diet,
        "vegan": "vegan" in diet,
        "jain": False,
        "satvik": (
            "sattvic" in diet or "satvik" in diet or "no onion no garlic" in diet
        ),
    }


def normalize_recipe(row):
    diet_flags = normalize_diet(row["Diet"])

    return {
        "recipe_id": f"R{int(row['Srno']):05d}",
        "recipe_name": clean_text(row["TranslatedRecipeName"]),
        "name_local": clean_text(row["RecipeName"]),
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
