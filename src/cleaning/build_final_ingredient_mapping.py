import pandas as pd
from pathlib import Path


# ---------------------------------------------------------
# FILES
# ---------------------------------------------------------

INPUT_FILE = Path("data/mappings/ingredient_candidates_normalized.csv")

PREVIOUS_MAPPING_FILE = Path("data/mappings/ingredient_mapping_review.csv")

OUTPUT_FILE = Path("data/mappings/final_ingredient_mapping.csv")


# ---------------------------------------------------------
# EXTRA NORMALIZED RULES
# ---------------------------------------------------------

NORMALIZED_RULES = {
    # -------------------------
    # Oils / liquids
    # -------------------------
    "sunflower oil": ("sunflower oil", "default"),
    "extra virgin olive oil": ("olive oil", "default"),
    "oil": ("cooking oil", "default"),
    "cooking oil": ("cooking oil", "default"),
    "water": ("water", "default"),
    "milk": ("milk", "default"),
    "coconut milk": ("coconut", "milk"),
    # -------------------------
    # Dairy
    # -------------------------
    "ghee": ("ghee", "default"),
    "butter": ("butter", "default"),
    "curd": ("curd", "default"),
    "hung curd": ("curd", "hung"),
    "fresh cream": ("cream", "fresh"),
    "paneer": ("paneer", "default"),
    "cheese": ("cheese", "default"),
    "mozzarella cheese": ("mozzarella", "default"),
    "parmesan cheese": ("parmesan", "default"),
    # -------------------------
    # Basic ingredients
    # -------------------------
    "salt": ("salt", "default"),
    "sugar": ("sugar", "default"),
    "brown sugar": ("brown sugar", "default"),
    "caster sugar": ("sugar", "caster"),
    "jaggery": ("jaggery", "default"),
    "honey": ("honey", "default"),
    # -------------------------
    # Vegetables
    # -------------------------
    "onion": ("onion", "default"),
    "onions": ("onion", "default"),
    "tomato": ("tomato", "default"),
    "tomatoes": ("tomato", "default"),
    "potato": ("potato", "default"),
    "potatoes": ("potato", "default"),
    "carrot": ("carrot", "default"),
    "carrots": ("carrot", "default"),
    "green bell pepper": ("green bell pepper", "default"),
    "red bell pepper": ("red bell pepper", "default"),
    "yellow bell pepper": ("yellow bell pepper", "default"),
    "green peas": ("green peas", "fresh"),
    "green beans": ("green beans", "default"),
    "cabbage": ("cabbage", "default"),
    "spinach": ("spinach", "default"),
    "broccoli": ("broccoli", "default"),
    "cauliflower": ("cauliflower", "default"),
    "cucumber": ("cucumber", "default"),
    "brinjal": ("brinjal", "default"),
    "kaddu": ("pumpkin", "default"),
    # -------------------------
    # Herbs
    # -------------------------
    "coriander leaves": ("coriander", "leaf"),
    "green coriander": ("coriander", "leaf"),
    "mint leaves": ("mint", "leaf"),
    "curry leaves": ("curry leaf", "default"),
    "bay leaf": ("bay leaf", "default"),
    "basil leaves": ("basil", "leaf"),
    "dried oregano": ("oregano", "dried"),
    "methi leaves": ("fenugreek leaves", "fresh"),
    # -------------------------
    # Spices
    # -------------------------
    "cumin seeds": ("cumin", "seed"),
    "cumin": ("cumin", "default"),
    "cumin powder": ("cumin", "powder"),
    "turmeric powder": ("turmeric", "powder"),
    "coriander seeds": ("coriander", "seed"),
    "coriander powder": ("coriander", "powder"),
    "mustard seeds": ("mustard", "seed"),
    "mustard": ("mustard", "default"),
    "fennel seeds": ("fennel", "seed"),
    "fennel": ("fennel", "default"),
    "methi seeds": ("fenugreek", "seed"),
    "fenugreek seeds": ("fenugreek", "seed"),
    "ajwain": ("ajwain", "default"),
    "asafoetida": ("asafoetida", "default"),
    "black pepper powder": ("black pepper", "powder"),
    "whole black peppercorns": ("black pepper", "whole"),
    "cardamom powder": ("cardamom", "powder"),
    "cardamom pods/seeds": ("cardamom", "pod"),
    "cinnamon stick": ("cinnamon", "stick"),
    "cinnamon powder": ("cinnamon", "powder"),
    "red chilli powder": ("red chilli", "powder"),
    "red chili powder": ("red chilli", "powder"),
    "red chilli flakes": ("red chilli", "flakes"),
    "dry red chilli": ("red chilli", "dried"),
    "dry red chillies": ("red chilli", "dried"),
    "kashmiri red chilli powder": ("kashmiri red chilli", "powder"),
    "garam masala powder": ("garam masala", "powder"),
    "chaat masala powder": ("chaat masala", "powder"),
    "sambar powder": ("sambar powder", "default"),
    "star anise": ("star anise", "default"),
    "paprika powder": ("paprika", "powder"),
    "saffron strands": ("saffron", "strand"),
    # -------------------------
    # Pulses / dals
    # -------------------------
    "chana dal": ("chana dal", "default"),
    "arhar dal": ("toor dal", "default"),
    "toor dal": ("toor dal", "default"),
    "yellow moong dal": ("moong dal", "default"),
    "white urad dal": ("urad dal", "white"),
    "kabuli chana": ("chickpea", "kabuli"),
    # -------------------------
    # Grains / flours
    # -------------------------
    "rice": ("rice", "default"),
    "basmati rice": ("rice", "basmati"),
    "sooji": ("semolina", "default"),
    "semolina": ("semolina", "default"),
    "all purpose flour": ("all purpose flour", "flour"),
    "whole wheat flour": ("whole wheat flour", "flour"),
    "gram flour": ("chickpea flour", "flour"),
    "rice flour": ("rice", "flour"),
    "corn flour": ("corn", "flour"),
    # -------------------------
    # Nuts / seeds
    # -------------------------
    "cashew nuts": ("cashew", "default"),
    "badam": ("almond", "default"),
    "almonds": ("almond", "default"),
    "raisins": ("raisin", "default"),
    "pistachios": ("pistachio", "default"),
    "walnuts": ("walnut", "default"),
    "raw peanuts": ("peanut", "raw"),
    "roasted peanuts": ("peanut", "roasted"),
    "peanuts": ("peanut", "default"),
    "sesame seeds": ("sesame", "seed"),
    "poppy seeds": ("poppy", "seed"),
    # -------------------------
    # Coconut
    # -------------------------
    "fresh coconut": ("coconut", "fresh"),
    "coconut": ("coconut", "default"),
    "desiccated coconut": ("coconut", "desiccated"),
    "dessicated coconut": ("coconut", "desiccated"),
    # -------------------------
    # Fruits
    # -------------------------
    "lemon": ("lemon", "default"),
    "lemon juice": ("lemon juice", "default"),
    "mango": ("mango", "default"),
    "ripe bananas": ("banana", "ripe"),
    "bananas": ("banana", "default"),
    "dates": ("date", "default"),
    # -------------------------
    # Sauces / condiments
    # -------------------------
    "soy sauce": ("soy sauce", "default"),
    "vinegar": ("vinegar", "default"),
    "red chilli sauce": ("red chilli", "sauce"),
    "tomato puree": ("tomato", "puree"),
    "homemade tomato puree": ("tomato", "puree"),
    # -------------------------
    # Baking
    # -------------------------
    "baking powder": ("baking powder", "default"),
    "baking soda": ("baking soda", "default"),
    "active dry yeast": ("yeast", "active dry"),
    "vanilla extract": ("vanilla", "default"),
    "cocoa powder": ("cocoa", "powder"),
    # -------------------------
    # Protein
    # -------------------------
    "chicken": ("chicken", "default"),
    "chicken breasts": ("chicken", "breast"),
    "mutton": ("mutton", "default"),
    "whole eggs": ("egg", "whole"),
    "whole egg": ("egg", "whole"),
    "egg": ("egg", "default"),
    "tofu": ("tofu", "default"),
    # -------------------------
    # Other
    # -------------------------
    "ginger garlic paste": ("ginger garlic", "paste"),
    "tamarind": ("tamarind", "default"),
    "tamarind paste": ("tamarind", "paste"),
    "amchur": ("amchur", "default"),
    "mustard oil": ("mustard", "oil"),
    "sesame oil": ("sesame", "oil"),
    "coconut oil": ("coconut", "oil"),
}


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------


def main():

    if not INPUT_FILE.exists():
        print(f"Input file not found: {INPUT_FILE}")
        return

    if not PREVIOUS_MAPPING_FILE.exists():
        print(f"Previous mapping file not found: {PREVIOUS_MAPPING_FILE}")
        return

    df = pd.read_csv(INPUT_FILE)

    previous = pd.read_csv(PREVIOUS_MAPPING_FILE, dtype=str)

    # Make sure required columns exist
    required_previous = {
        "candidate_ingredient",
        "canonical_ingredient",
        "ingredient_form",
        "mapping_status",
    }

    missing = required_previous - set(previous.columns)

    if missing:
        print("Previous mapping file is missing columns:", ", ".join(sorted(missing)))
        return

    # Normalize previous mapping columns
    for column in [
        "candidate_ingredient",
        "canonical_ingredient",
        "ingredient_form",
        "mapping_status",
    ]:
        previous[column] = previous[column].fillna("").astype(str).str.strip()

    previous["candidate_key"] = previous["candidate_ingredient"].str.lower().str.strip()

    previous_auto = previous[previous["mapping_status"].str.upper() == "AUTO"].copy()

    previous_auto = previous_auto.drop_duplicates(
        subset=["candidate_key"], keep="first"
    )

    previous_auto_lookup = {
        row["candidate_key"]: (row["canonical_ingredient"], row["ingredient_form"])
        for _, row in previous_auto.iterrows()
    }

    # -----------------------------------------------------
    # Prepare final columns
    # -----------------------------------------------------

    df["final_canonical_ingredient"] = pd.Series("", index=df.index, dtype="string")

    df["final_ingredient_form"] = pd.Series("", index=df.index, dtype="string")

    df["final_mapping_status"] = pd.Series("REVIEW", index=df.index, dtype="string")

    # -----------------------------------------------------
    # Mapping
    # -----------------------------------------------------

    previous_auto_count = 0
    normalized_count = 0
    review_count = 0

    for i, row in df.iterrows():
        original_candidate = str(row["candidate_ingredient"]).strip().lower()

        normalized_candidate = str(row["normalized_candidate"]).strip().lower()

        # ---------------------------------------------
        # 1. Use previous successful AUTO mapping
        # ---------------------------------------------

        if original_candidate in previous_auto_lookup:
            canonical, form = previous_auto_lookup[original_candidate]

            df.at[i, "final_canonical_ingredient"] = canonical
            df.at[i, "final_ingredient_form"] = form
            df.at[i, "final_mapping_status"] = "AUTO"

            previous_auto_count += 1

        # ---------------------------------------------
        # 2. Apply normalized rules
        # ---------------------------------------------

        elif normalized_candidate in NORMALIZED_RULES:
            canonical, form = NORMALIZED_RULES[normalized_candidate]

            df.at[i, "final_canonical_ingredient"] = canonical
            df.at[i, "final_ingredient_form"] = form
            df.at[i, "final_mapping_status"] = "AUTO"

            normalized_count += 1

        # ---------------------------------------------
        # 3. Leave for manual review
        # ---------------------------------------------

        else:
            df.at[i, "final_mapping_status"] = "REVIEW"

            review_count += 1

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    # -----------------------------------------------------
    # Statistics
    # -----------------------------------------------------

    total = len(df)

    auto_total = df["final_mapping_status"].eq("AUTO").sum()

    review_total = df["final_mapping_status"].eq("REVIEW").sum()

    print("=" * 70)
    print("FINAL INGREDIENT MAPPING")
    print("=" * 70)

    print(f"\nTotal candidates: {total}")
    print(f"Previous automatic mappings reused: {previous_auto_count}")
    print(f"New normalized mappings: {normalized_count}")
    print(f"Automatically mapped: {auto_total}")
    print(f"Remaining for review: {review_total}")

    print(f"\nOutput: {OUTPUT_FILE}")

    # -----------------------------------------------------
    # AUTO examples
    # -----------------------------------------------------

    print("\n" + "=" * 70)
    print("AUTOMATIC MAPPINGS")
    print("=" * 70)

    auto_df = df[df["final_mapping_status"] == "AUTO"]

    print(
        auto_df[
            [
                "candidate_ingredient",
                "cleaned_candidate",
                "normalized_candidate",
                "final_canonical_ingredient",
                "final_ingredient_form",
                "frequency",
            ]
        ]
        .head(100)
        .to_string(index=False)
    )

    # -----------------------------------------------------
    # REVIEW examples
    # -----------------------------------------------------

    print("\n" + "=" * 70)
    print("REMAINING REVIEW CANDIDATES")
    print("=" * 70)

    review_df = df[df["final_mapping_status"] == "REVIEW"]

    print(
        review_df[
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
