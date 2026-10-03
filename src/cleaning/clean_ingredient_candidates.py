import pandas as pd
import re
from pathlib import Path


INPUT_FILE = Path("data/mappings/ingredient_mapping_review.csv")

OUTPUT_FILE = Path("data/mappings/ingredient_candidates_cleaned.csv")


# Words/phrases that describe quantity or preparation,
# rather than the ingredient itself.
CLEANUP_PATTERNS = [
    # English quantity descriptors
    r"^\s*pinch\s+",
    r"^\s*small\s+teaspoon\s+",
    r"^\s*small\s+tsp\s+",
    r"^\s*large\s+teaspoon\s+",
    r"^\s*large\s+tsp\s+",
    # Hindi quantity descriptors
    r"^\s*छोटा\s+चमच्च\s+",
    r"^\s*छोटा\s+चम्मच\s+",
    r"^\s*बड़ा\s+चमच्च\s+",
    r"^\s*बड़ा\s+चम्मच\s+",
    # Hindi preparation/quantity descriptors
    r"^\s*इंच\s+",
    r"^\s*कली\s+",
    r"^\s*टहनी\s+",
]


# Preparation words that sometimes appear at the
# beginning of the candidate ingredient.
PREPARATION_PREFIXES = [
    "lukewarm ",
    "homemade ",
    "freshly ",
    "roasted ",
    "boiled ",
    "cooked ",
    "raw ",
    "ripe ",
]


def clean_candidate(text):
    """
    Remove obvious quantity/preparation prefixes
    while keeping the original candidate unchanged.
    """

    if pd.isna(text):
        return ""

    text = str(text).strip().lower()

    # Remove quantity descriptors
    for pattern in CLEANUP_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Remove preparation prefixes
    for prefix in PREPARATION_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def main():

    if not INPUT_FILE.exists():
        print(f"Input file not found: {INPUT_FILE}")
        return

    df = pd.read_csv(INPUT_FILE)

    # Create cleaned candidate column
    df["cleaned_candidate"] = df["candidate_ingredient"].apply(clean_candidate)

    # Determine whether cleanup changed the candidate
    df["cleanup_status"] = "UNCHANGED"

    df.loc[
        df["candidate_ingredient"].astype(str).str.lower() != df["cleaned_candidate"],
        "cleanup_status",
    ] = "CLEANED"

    # Save result
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    print("=" * 70)
    print("INGREDIENT CANDIDATE CLEANUP")
    print("=" * 70)

    print(f"\nTotal candidates: {len(df)}")

    print(f"Candidates cleaned: {(df['cleanup_status'] == 'CLEANED').sum()}")

    print(f"Candidates unchanged: {(df['cleanup_status'] == 'UNCHANGED').sum()}")

    print(f"\nOutput: {OUTPUT_FILE}")

    print("\nExamples of cleaned candidates:")

    cleaned = df[df["cleanup_status"] == "CLEANED"]

    print(
        cleaned[["candidate_ingredient", "cleaned_candidate", "frequency"]]
        .head(50)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
