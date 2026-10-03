import pandas as pd
from pathlib import Path


INPUT_FILE = Path("data/mappings/ingredient_candidates_cleaned.csv")

OUTPUT_FILE = Path("data/mappings/ingredient_candidates_normalized.csv")


HINDI_MAP = {
    # Spices
    "हल्दी पाउडर": "turmeric powder",
    "जीरा": "cumin",
    "जीरा पाउडर": "cumin powder",
    "धनिया पाउडर": "coriander powder",
    "धनिया": "coriander",
    "सौंफ": "fennel",
    "सौंफ के दाने": "fennel seeds",
    "हींग": "asafoetida",
    "गरम मसाला पाउडर": "garam masala powder",
    "लाल मिर्च पाउडर": "red chilli powder",
    "काली मिर्च पाउडर": "black pepper powder",
    "पूरी काली मिर्च": "whole black peppercorns",
    "दाल चीनी": "cinnamon stick",
    "दालचीनी": "cinnamon stick",
    "राइ": "mustard seeds",
    "मेथी के दाने": "fenugreek seeds",
    # Vegetables / herbs
    "अदरक": "ginger",
    "लहसुन": "garlic",
    "हरा धनिया": "coriander leaves",
    "कढ़ी पत्ता": "curry leaves",
    # Pulses
    "सफ़ेद उरद दाल": "white urad dal",
    "सफेद उरद दाल": "white urad dal",
    # Pastes / liquids
    "अदरक लहसुन का पेस्ट": "ginger garlic paste",
    "निम्बू का रस": "lemon juice",
    # Oils / sweeteners
    "तेल": "cooking oil",
    "शक्कर": "sugar",
}


def normalize_hindi(text):

    if pd.isna(text):
        return ""

    text = str(text).strip().lower()

    return HINDI_MAP.get(text, text)


def main():

    if not INPUT_FILE.exists():
        print(f"Input file not found: {INPUT_FILE}")
        return

    df = pd.read_csv(INPUT_FILE)

    df["normalized_candidate"] = df["cleaned_candidate"].apply(normalize_hindi)

    df["normalization_status"] = "UNCHANGED"

    df.loc[
        df["normalized_candidate"].astype(str) != df["cleaned_candidate"].astype(str),
        "normalization_status",
    ] = "NORMALIZED"

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    print("=" * 70)
    print("HINDI INGREDIENT NORMALIZATION")
    print("=" * 70)

    print(f"\nTotal candidates: {len(df)}")

    print(
        "Hindi candidates normalized: "
        f"{(df['normalization_status'] == 'NORMALIZED').sum()}"
    )

    print(f"Unchanged: {(df['normalization_status'] == 'UNCHANGED').sum()}")

    print(f"\nOutput: {OUTPUT_FILE}")

    print("\nExamples:")

    normalized = df[df["normalization_status"] == "NORMALIZED"]

    print(
        normalized[
            [
                "candidate_ingredient",
                "cleaned_candidate",
                "normalized_candidate",
                "frequency",
            ]
        ]
        .head(50)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
