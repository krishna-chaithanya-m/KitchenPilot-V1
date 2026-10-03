import pandas as pd
from pathlib import Path


INPUT_FILE = Path("data/mappings/ingredient_mapping_review.csv")
OUTPUT_FILE = Path("data/mappings/ingredient_mapping_review.csv")


DIRECT_MAP = {
    # ============================================================
    # SALT
    # ============================================================
    "नमक": "salt",
    "salt": "salt",
    # ============================================================
    # ONION
    # ============================================================
    "onions": "onion",
    "onion": "onion",
    "प्याज": "onion",
    # ============================================================
    # TOMATO
    # ============================================================
    "tomatoes": "tomato",
    "tomato": "tomato",
    "टमाटर": "tomato",
    # ============================================================
    # GREEN CHILLI
    # ============================================================
    "green chillies": "green chilli",
    "green chilli": "green chilli",
    "हरी मिर्च": "green chilli",
    # ============================================================
    # RED CHILLI
    # ============================================================
    "dry red chillies": "dry red chilli",
    # ============================================================
    # POTATO
    # ============================================================
    "potatoes": "potato",
    "potato": "potato",
    # ============================================================
    # CARROT
    # ============================================================
    "carrots": "carrot",
    "carrot": "carrot",
    # ============================================================
    # EGG
    # ============================================================
    "whole eggs": "egg",
    "whole egg": "egg",
    # ============================================================
    # COMMON HERBS
    # ============================================================
    "curry leaves": "curry leaf",
    "mint leaves": "mint leaf",
    "bay leaf": "bay leaf",
    "bay leaves": "bay leaf",
    # ============================================================
    # BASIC INGREDIENTS
    # ============================================================
    "garlic": "garlic",
    "ginger": "ginger",
    "sugar": "sugar",
    "water": "water",
    "ghee": "ghee",
    "butter": "butter",
    "milk": "milk",
    "curd": "curd",
    "jaggery": "jaggery",
    "honey": "honey",
    # ============================================================
    # OILS
    # ============================================================
    "sunflower oil": "sunflower oil",
    "extra virgin olive oil": "olive oil",
    "coconut oil": "coconut oil",
    "oil": "cooking oil",
    "तेल": "cooking oil",
    # ============================================================
    # PULSES / DAL
    # ============================================================
    "chana dal": "chana dal",
    "arhar dal": "toor dal",
    "yellow moong dal": "moong dal",
    # ============================================================
    # VEGETABLES
    # ============================================================
    "green bell pepper": "green bell pepper",
    "red bell pepper": "red bell pepper",
    "green beans": "green beans",
    "sweet corn": "sweet corn",
    "cabbage": "cabbage",
    "spinach": "spinach",
    "spinach leaves": "spinach",
    "broccoli": "broccoli",
    "cauliflower": "cauliflower",
    "cucumber": "cucumber",
    # ============================================================
    # FRUITS
    # ============================================================
    "lemon": "lemon",
    "mango": "mango",
    # ============================================================
    # NUTS
    # ============================================================
    "cashew nuts": "cashew",
    "badam": "almond",
    "raisins": "raisin",
    "pistachios": "pistachio",
    "walnuts": "walnut",
    "roasted peanuts": "peanut",
    # ============================================================
    # HERBS / SPICES
    # ============================================================
    "asafoetida": "asafoetida",
    "ajwain": "ajwain",
    "dried oregano": "oregano",
    "basil leaves": "basil",
    "parsley leaves": "parsley",
    "kasuri methi": "fenugreek leaves",
    # ============================================================
    # MASALA / SAUCES
    # ============================================================
    "chaat masala powder": "chaat masala",
    "soy sauce": "soy sauce",
    # ============================================================
    # GRAINS / FLOURS
    # ============================================================
    "rice": "rice",
    "sooji": "semolina",
    "instant oats": "oats",
    # ============================================================
    # BAKING
    # ============================================================
    "baking powder": "baking powder",
    "baking soda": "baking soda",
    # ============================================================
    # DAIRY
    # ============================================================
    "paneer": "paneer",
    "mozzarella cheese": "mozzarella",
    # ============================================================
    # MEAT
    # ============================================================
    "chicken": "chicken",
    "chicken breasts": "chicken",
    # ============================================================
    # OTHER
    # ============================================================
    "vanilla extract": "vanilla",
    "amchur": "amchur",
    "tamarind": "tamarind",
    "button mushrooms": "button mushroom",
}


FORM_RULES = {
    # ============================================================
    # SPICES
    # ============================================================
    "cumin seeds": ("cumin", "seed"),
    "cumin powder": ("cumin", "powder"),
    "turmeric powder": ("turmeric", "powder"),
    "coriander seeds": ("coriander", "seed"),
    "coriander powder": ("coriander", "powder"),
    "coriander leaves": ("coriander", "leaf"),
    "mustard seeds": ("mustard", "seed"),
    "mustard": ("mustard", "default"),
    "fennel seeds": ("fennel", "seed"),
    "sesame seeds": ("sesame", "seed"),
    "black pepper powder": ("black pepper", "powder"),
    "whole black peppercorns": ("black pepper", "whole"),
    "cardamom powder": ("cardamom", "powder"),
    "cardamom pods/seeds": ("cardamom", "pod"),
    "cinnamon stick": ("cinnamon", "stick"),
    "cinnamon powder": ("cinnamon", "powder"),
    "red chilli powder": ("red chilli", "powder"),
    "kashmiri red chilli powder": (
        "kashmiri red chilli",
        "powder",
    ),
    "red chilli flakes": ("red chilli", "flakes"),
    "dry red chilli": ("red chilli", "dried"),
    # ============================================================
    # FLOURS
    # ============================================================
    "gram flour": ("chickpea flour", "flour"),
    "all purpose flour": ("all purpose flour", "flour"),
    "whole wheat flour": ("whole wheat flour", "flour"),
    "rice flour": ("rice", "flour"),
    "corn flour": ("corn", "flour"),
    # ============================================================
    # COCONUT
    # ============================================================
    "fresh coconut": ("coconut", "fresh"),
    "coconut milk": ("coconut", "milk"),
    # ============================================================
    # PASTES
    # ============================================================
    "ginger garlic paste": ("ginger garlic", "paste"),
    "tamarind paste": ("tamarind", "paste"),
    "tamarind water": ("tamarind", "water"),
    # ============================================================
    # PEAS / CREAM / CURD
    # ============================================================
    "green peas": ("green peas", "fresh"),
    "fresh cream": ("cream", "fresh"),
    "hung curd": ("curd", "hung"),
    # ============================================================
    # MASALA
    # ============================================================
    "garam masala powder": ("garam masala", "powder"),
    # ============================================================
    # FENUGREEK
    # ============================================================
    "methi seeds": ("fenugreek", "seed"),
    # ============================================================
    # OILS
    # ============================================================
    "mustard oil": ("mustard", "oil"),
    "sesame oil": ("sesame", "oil"),
    # ============================================================
    # DAL
    # ============================================================
    "white urad dal": ("urad dal", "white"),
    # ============================================================
    # OTHER FORMS
    # ============================================================
    "saffron strands": ("saffron", "strand"),
    "poppy seeds": ("poppy", "seed"),
    "red chilli sauce": ("red chilli", "sauce"),
}


def main():

    if not INPUT_FILE.exists():
        print(f"Input file not found: {INPUT_FILE}")
        return

    df = pd.read_csv(INPUT_FILE)

    # Prevent pandas dtype warnings
    df["canonical_ingredient"] = df["canonical_ingredient"].fillna("").astype("string")

    df["ingredient_form"] = df["ingredient_form"].fillna("").astype("string")

    df["category"] = df["category"].fillna("").astype("string")

    df["mapping_status"] = df["mapping_status"].fillna("REVIEW").astype("string")

    mapped = 0

    for i, row in df.iterrows():
        candidate = str(row["candidate_ingredient"]).strip().lower()

        # --------------------------------------------------------
        # Direct mapping
        # --------------------------------------------------------

        if candidate in DIRECT_MAP:
            df.at[i, "canonical_ingredient"] = DIRECT_MAP[candidate]

            df.at[i, "ingredient_form"] = "default"
            df.at[i, "mapping_status"] = "AUTO"

            mapped += 1

        # --------------------------------------------------------
        # Form-aware mapping
        # --------------------------------------------------------

        elif candidate in FORM_RULES:
            canonical, form = FORM_RULES[candidate]

            df.at[i, "canonical_ingredient"] = canonical
            df.at[i, "ingredient_form"] = form
            df.at[i, "mapping_status"] = "AUTO"

            mapped += 1

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    print("=" * 70)
    print("EXPANDED AUTOMATIC INGREDIENT MAPPING")
    print("=" * 70)

    print(f"\nTotal candidates: {len(df)}")
    print(f"Automatically mapped: {mapped}")
    print(f"Remaining for review: {len(df) - mapped}")

    print("\nAutomatic mappings:")

    print(df[df["mapping_status"] == "AUTO"].head(100).to_string(index=False))

    print("\nRemaining REVIEW candidates:")

    print(df[df["mapping_status"] == "REVIEW"].head(50).to_string(index=False))


if __name__ == "__main__":
    main()
