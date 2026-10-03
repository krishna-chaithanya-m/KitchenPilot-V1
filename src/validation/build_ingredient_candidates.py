import pandas as pd
import re
from pathlib import Path


INPUT_FILE = Path("data/processed/recipe_ingredients.csv")

OUTPUT_FILE = Path("data/mappings/ingredient_candidates.csv")


def normalize_candidate(text):

    if pd.isna(text):
        return ""

    text = str(text).strip().lower()

    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)

    # Remove common parenthetical translations
    # Example:
    # turmeric powder (haldi)
    # -> turmeric powder
    text = re.sub(r"\s*\([^)]*\)", "", text)

    # Remove trailing punctuation
    text = text.strip(" .")

    return text


def main():

    if not INPUT_FILE.exists():
        print(f"Input file not found: {INPUT_FILE}")

        return

    df = pd.read_csv(INPUT_FILE)

    candidates = df["ingredient"].dropna().map(normalize_candidate)

    candidates = candidates[candidates != ""]

    counts = candidates.value_counts().reset_index()

    counts.columns = ["candidate_ingredient", "frequency"]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    counts.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    print("=" * 70)
    print("INGREDIENT CANDIDATES CREATED")
    print("=" * 70)

    print(f"\nParsed ingredient records: {len(df)}")

    print(f"Unique candidates: {len(counts)}")

    print(f"\nOutput: {OUTPUT_FILE}")

    print("\nTop 100 candidates:")

    print(counts.head(100).to_string(index=False))


if __name__ == "__main__":
    main()
