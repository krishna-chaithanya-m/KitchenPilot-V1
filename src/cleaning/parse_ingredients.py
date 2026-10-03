import pandas as pd
import re
from pathlib import Path


DATA_FILE = Path("data/processed/recipes.csv")
OUTPUT_FILE = Path("data/processed/recipe_ingredients.csv")


UNITS = [
    "tablespoons",
    "tablespoon",
    "tbsp",
    "teaspoons",
    "teaspoon",
    "tsp",
    "cups",
    "cup",
    "grams",
    "gram",
    "kilograms",
    "kilogram",
    "kg",
    "milliliters",
    "milliliter",
    "ml",
    "litres",
    "liters",
    "litre",
    "liter",
    "inch",
    "inches",
    "cloves",
    "clove",
    "sprigs",
    "sprig",
    "pieces",
    "piece",
    "bunch",
    "bunches",
]


def clean_text(text):
    if pd.isna(text):
        return ""

    return " ".join(str(text).split()).strip()


def parse_quantity(text):

    text = text.strip()

    # Mixed fractions such as:
    # 2-1 / 2
    # 1-1/2
    mixed_fraction = re.match(r"^(\d+)\s*-\s*(\d+)\s*/\s*(\d+)", text)

    if mixed_fraction:
        whole = mixed_fraction.group(1)
        numerator = mixed_fraction.group(2)
        denominator = mixed_fraction.group(3)

        quantity = f"{whole} {numerator}/{denominator}"

        remaining = text[mixed_fraction.end() :].strip()

        return quantity, remaining

    # Normal fraction:
    # 1/2
    fraction = re.match(r"^(\d+)\s*/\s*(\d+)", text)

    if fraction:
        quantity = f"{fraction.group(1)}/{fraction.group(2)}"

        remaining = text[fraction.end() :].strip()

        return quantity, remaining

    # Decimal / integer
    number = re.match(r"^(\d+(?:\.\d+)?)", text)

    if number:
        quantity = number.group(1)

        remaining = text[number.end() :].strip()

        return quantity, remaining

    return "", text


def parse_unit(text):

    text_lower = text.lower()

    # Longest units first
    sorted_units = sorted(UNITS, key=len, reverse=True)

    for unit in sorted_units:
        pattern = rf"^{re.escape(unit)}\b"

        match = re.match(pattern, text_lower)

        if match:
            remaining = text[match.end() :].strip()

            return unit, remaining

    return "", text


def split_preparation(text):

    # Dataset frequently uses:
    # ingredient - chopped
    # ingredient - finely chopped

    parts = re.split(r"\s+-\s+", text, maxsplit=1)

    ingredient = parts[0].strip()

    preparation = ""

    if len(parts) == 2:
        preparation = parts[1].strip()

    return ingredient, preparation


def parse_ingredient(raw):

    raw = clean_text(raw)

    if not raw:
        return None

    original = raw

    # Remove accidental leading/trailing spaces
    raw = raw.strip()

    quantity, remaining = parse_quantity(raw)

    unit, remaining = parse_unit(remaining)

    ingredient, preparation = split_preparation(remaining)

    ingredient = clean_text(ingredient)
    preparation = clean_text(preparation)

    return {
        "original_ingredient": original,
        "quantity": quantity,
        "unit": unit,
        "ingredient": ingredient,
        "preparation": preparation,
    }


def main():

    if not DATA_FILE.exists():
        print(f"Dataset not found: {DATA_FILE}")

        return

    df = pd.read_csv(DATA_FILE)

    records = []

    for _, recipe in df.iterrows():
        ingredients_text = recipe["ingredients"]

        if pd.isna(ingredients_text):
            continue

        ingredients = str(ingredients_text).split(",")

        for raw_ingredient in ingredients:
            parsed = parse_ingredient(raw_ingredient)

            if parsed:
                parsed["recipe_id"] = recipe["recipe_id"]

                records.append(parsed)

    result = pd.DataFrame(records)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    result.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    print("=" * 70)
    print("INGREDIENT PARSING COMPLETE")
    print("=" * 70)

    print(f"\nRecipes processed: {len(df)}")

    print(f"Ingredient records: {len(result)}")

    print(f"\nOutput: {OUTPUT_FILE}")

    print("\nSample:")
    print(result.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
