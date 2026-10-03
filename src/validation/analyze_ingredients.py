import pandas as pd
import re
from collections import Counter
from pathlib import Path


DATA_FILE = Path("data/processed/recipes.csv")


def extract_ingredient_names(text):
    if pd.isna(text) or not str(text).strip():
        return []

    ingredients = str(text).split(",")

    cleaned = []

    for ingredient in ingredients:
        ingredient = ingredient.strip().lower()

        # Remove quantities at the beginning
        ingredient = re.sub(r"^[\d\s./½¼¾⅓⅔-]+", "", ingredient)

        # Remove common measurement words
        ingredient = re.sub(
            r"\b(cups?|tablespoons?|tbsp|"
            r"teaspoons?|tsp|grams?|kg|ml|litres?|liters?)\b",
            "",
            ingredient,
        )

        ingredient = ingredient.strip()

        if ingredient:
            cleaned.append(ingredient)

    return cleaned


def main():

    if not DATA_FILE.exists():
        print(f"Dataset not found: {DATA_FILE}")
        return

    df = pd.read_csv(DATA_FILE)

    counter = Counter()

    for ingredients in df["ingredients"]:
        for ingredient in extract_ingredient_names(ingredients):
            counter[ingredient] += 1

    print("=" * 70)
    print("INGREDIENT ANALYSIS")
    print("=" * 70)

    print(f"\nRecipes analyzed: {len(df)}")
    print(f"Unique ingredient strings: {len(counter)}")

    print("\nTop 100 ingredient strings:")

    for ingredient, count in counter.most_common(100):
        print(f"{count:5}  {ingredient}")


if __name__ == "__main__":
    main()
