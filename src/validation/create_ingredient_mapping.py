import pandas as pd
from pathlib import Path

INPUT_FILE = Path("data/mappings/ingredient_candidates.csv")
OUTPUT_FILE = Path("data/mappings/ingredient_mapping_review.csv")


def main():
    if not INPUT_FILE.exists():
        print(f"Input file not found: {INPUT_FILE}")
        return

    df = pd.read_csv(INPUT_FILE)

    mapping = pd.DataFrame(
        {
            "candidate_ingredient": df["candidate_ingredient"],
            "frequency": df["frequency"],
            "canonical_ingredient": "",
            "ingredient_form": "",
            "category": "",
            "mapping_status": "REVIEW",
        }
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    print("=" * 70)
    print("INGREDIENT MAPPING REVIEW FILE CREATED")
    print("=" * 70)

    print(f"\nCandidates: {len(mapping)}")
    print(f"Output: {OUTPUT_FILE}")

    print("\nFirst 50 candidates requiring review:")
    print(mapping.head(50).to_string(index=False))


if __name__ == "__main__":
    main()
