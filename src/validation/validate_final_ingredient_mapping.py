import pandas as pd
from pathlib import Path


# ---------------------------------------------------------
# FILES
# ---------------------------------------------------------

INPUT_FILE = Path("data/mappings/final_ingredient_mapping.csv")

OUTPUT_FILE = Path("data/mappings/final_ingredient_mapping_validated.csv")


# ---------------------------------------------------------
# VALID CANONICAL/FORMS
# ---------------------------------------------------------

VALID_FORMS = {
    "default",
    "powder",
    "seed",
    "leaf",
    "whole",
    "pod",
    "stick",
    "paste",
    "fresh",
    "dried",
    "flakes",
    "flour",
    "milk",
    "oil",
    "hung",
    "caster",
    "raw",
    "roasted",
    "ripe",
    "basmati",
    "breast",
    "strand",
    "puree",
    "active dry",
    "kabuli",
    "desiccated",
    "white",
}


# ---------------------------------------------------------
# KNOWN CORRECTIONS
#
# These correct malformed canonical values created by
# previous mapping layers.
# ---------------------------------------------------------

CORRECTIONS = {
    # Coconut
    "coconutfresh": ("coconut", "fresh"),
    # Cinnamon
    "cinnamonstick": ("cinnamon", "stick"),
    # Flour
    "all purpose flourflour": ("all purpose flour", "flour"),
    "whole wheat flourflour": ("whole wheat flour", "flour"),
    "chickpea flourflour": ("chickpea flour", "flour"),
    "cornflour": ("corn", "flour"),
    "riceflour": ("rice", "flour"),
    # Dal
    "urad dalwhite": ("urad dal", "white"),
    # Pepper
    "black pepperwhole": ("black pepper", "whole"),
    # Ginger garlic
    "ginger garlicpaste": ("ginger garlic", "paste"),
    # Chilli
    "red chillidried": ("red chilli", "dried"),
    # Green peas
    "green peasfresh": ("green peas", "fresh"),
    # Cream
    "creamfresh": ("cream", "fresh"),
    # Tomato
    "tomatopuree": ("tomato", "puree"),
    # Fenugreek
    "fenugreekseed": ("fenugreek", "seed"),
    # Mustard / sesame
    "mustard oil": ("mustard", "oil"),
    "sesame oil": ("sesame", "oil"),
}


# ---------------------------------------------------------
# SUSPICIOUS PATTERNS
# ---------------------------------------------------------

SUSPICIOUS_COMBINATIONS = [
    "coconutfresh",
    "cinnamonstick",
    "flourflour",
    "dalwhite",
    "pepperwhole",
    "paste",
    "cornflour",
    "riceflour",
    "peasfresh",
    "creamfresh",
    "tomatopuree",
    "seed",
]


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------


def clean_text(value):
    """
    Safely convert a value to normalized lowercase text.
    """
    if pd.isna(value):
        return ""

    return str(value).strip().lower()


def is_suspicious(canonical, form):
    """
    Detect malformed canonical/form combinations.
    """

    canonical = clean_text(canonical)
    form = clean_text(form)

    # Empty canonical value
    if canonical == "":
        return True

    # Empty form for AUTO mapping
    if form == "":
        return True

    # Invalid form
    if form not in VALID_FORMS:
        return True

    # Canonical value contains the form directly
    # e.g. "cinnamonstick" + "stick"
    if form != "default":
        if canonical.endswith(form):
            return True

    # Explicit known malformed values
    if canonical in CORRECTIONS:
        return True

    return False


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------


def main():

    if not INPUT_FILE.exists():
        print(f"Input file not found: {INPUT_FILE}")
        return

    df = pd.read_csv(INPUT_FILE, dtype=str)

    # -----------------------------------------------------
    # Normalize columns
    # -----------------------------------------------------

    required_columns = [
        "candidate_ingredient",
        "cleaned_candidate",
        "normalized_candidate",
        "final_canonical_ingredient",
        "final_ingredient_form",
        "final_mapping_status",
        "frequency",
    ]

    missing_columns = [
        column for column in required_columns if column not in df.columns
    ]

    if missing_columns:
        print("Missing required columns:", ", ".join(missing_columns))
        return

    for column in required_columns:
        df[column] = df[column].fillna("").astype(str).str.strip()

    # -----------------------------------------------------
    # New validation columns
    # -----------------------------------------------------

    df["validation_status"] = "VALID"

    df["validation_note"] = ""

    # -----------------------------------------------------
    # Process automatic mappings
    # -----------------------------------------------------

    correction_count = 0
    suspicious_count = 0
    valid_count = 0

    for i, row in df.iterrows():
        status = clean_text(row["final_mapping_status"])

        canonical = clean_text(row["final_canonical_ingredient"])

        form = clean_text(row["final_ingredient_form"])

        # -------------------------------------------------
        # REVIEW records
        # -------------------------------------------------

        if status == "review":
            df.at[i, "validation_status"] = "REVIEW"

            df.at[i, "validation_note"] = "Requires ingredient mapping review"

            continue

        # -------------------------------------------------
        # AUTO records
        # -------------------------------------------------

        if status == "auto":
            # ---------------------------------------------
            # Known correction
            # ---------------------------------------------

            if canonical in CORRECTIONS:
                corrected_canonical, corrected_form = CORRECTIONS[canonical]

                df.at[i, "final_canonical_ingredient"] = corrected_canonical

                df.at[i, "final_ingredient_form"] = corrected_form

                df.at[i, "validation_status"] = "CORRECTED"

                df.at[i, "validation_note"] = (
                    f"Corrected malformed mapping: {canonical} → {corrected_canonical}"
                )

                correction_count += 1

                continue

            # ---------------------------------------------
            # General suspicious mapping detection
            # ---------------------------------------------

            if is_suspicious(canonical, form):
                df.at[i, "validation_status"] = "SUSPICIOUS"

                df.at[i, "validation_note"] = "Automatic mapping requires review"

                suspicious_count += 1

                continue

            # ---------------------------------------------
            # Valid
            # ---------------------------------------------

            df.at[i, "validation_status"] = "VALID"

            df.at[i, "validation_note"] = "Validated automatic mapping"

            valid_count += 1

        else:
            df.at[i, "validation_status"] = "REVIEW"

            df.at[i, "validation_note"] = "Unknown mapping status"

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    # -----------------------------------------------------
    # Statistics
    # -----------------------------------------------------

    total = len(df)

    auto_total = df["final_mapping_status"].str.upper().eq("AUTO").sum()

    review_total = df["final_mapping_status"].str.upper().eq("REVIEW").sum()

    validated_total = df["validation_status"].eq("VALID").sum()

    corrected_total = df["validation_status"].eq("CORRECTED").sum()

    suspicious_total = df["validation_status"].eq("SUSPICIOUS").sum()

    validation_review_total = df["validation_status"].eq("REVIEW").sum()

    # -----------------------------------------------------
    # Output
    # -----------------------------------------------------

    print("=" * 70)
    print("FINAL INGREDIENT MAPPING VALIDATION")
    print("=" * 70)

    print(f"\nTotal candidates: {total}")

    print(f"Automatic mappings before validation: {auto_total}")

    print(f"Review mappings before validation: {review_total}")

    print("\nValidation results:")

    print(f"Valid automatic mappings: {validated_total}")

    print(f"Corrected mappings: {corrected_total}")

    print(f"Suspicious automatic mappings: {suspicious_total}")

    print(f"Review candidates: {validation_review_total}")

    print(f"\nOutput: {OUTPUT_FILE}")

    # -----------------------------------------------------
    # Corrected mappings
    # -----------------------------------------------------

    print("\n" + "=" * 70)
    print("CORRECTED MAPPINGS")
    print("=" * 70)

    corrected = df[df["validation_status"] == "CORRECTED"]

    if len(corrected) > 0:
        print(
            corrected[
                [
                    "candidate_ingredient",
                    "final_canonical_ingredient",
                    "final_ingredient_form",
                    "validation_note",
                    "frequency",
                ]
            ].to_string(index=False)
        )

    else:
        print("No corrections required.")

    # -----------------------------------------------------
    # Suspicious mappings
    # -----------------------------------------------------

    print("\n" + "=" * 70)
    print("SUSPICIOUS MAPPINGS")
    print("=" * 70)

    suspicious = df[df["validation_status"] == "SUSPICIOUS"]

    if len(suspicious) > 0:
        print(
            suspicious[
                [
                    "candidate_ingredient",
                    "final_canonical_ingredient",
                    "final_ingredient_form",
                    "validation_note",
                    "frequency",
                ]
            ]
            .head(100)
            .to_string(index=False)
        )

    else:
        print("No suspicious automatic mappings found.")

    # -----------------------------------------------------
    # Top remaining review candidates
    # -----------------------------------------------------

    print("\n" + "=" * 70)
    print("TOP REVIEW CANDIDATES")
    print("=" * 70)

    review = df[df["validation_status"] == "REVIEW"]

    print(
        review[
            [
                "candidate_ingredient",
                "cleaned_candidate",
                "normalized_candidate",
                "frequency",
            ]
        ]
        .head(100)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
