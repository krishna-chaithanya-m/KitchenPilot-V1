import pandas as pd
from pathlib import Path


# ---------------------------------------------------------
# FILES
# ---------------------------------------------------------

MAPPING_FILE = Path("data/mappings/final_ingredient_mapping_validated.csv")

OUTPUT_FILE = Path("data/processed/ingredients.csv")


# ---------------------------------------------------------
# CATEGORY RULES
# ---------------------------------------------------------

CATEGORY_RULES = {
    # Spices
    "turmeric": "spice",
    "cumin": "spice",
    "coriander": "spice",
    "mustard": "spice",
    "fennel": "spice",
    "fenugreek": "spice",
    "asafoetida": "spice",
    "black pepper": "spice",
    "cardamom": "spice",
    "cinnamon": "spice",
    "red chilli": "spice",
    "kashmiri red chilli": "spice",
    "garam masala": "spice",
    "chaat masala": "spice",
    "sambar powder": "spice",
    "ajwain": "spice",
    "star anise": "spice",
    "paprika": "spice",
    "saffron": "spice",
    "nutmeg": "spice",
    "mace": "spice",
    "kalonji": "spice",
    "anardana": "spice",
    "kokum": "spice",
    "amchur": "spice",
    "panch phoran masala": "spice",
    "italian seasoning": "spice",
    # Seasonings
    "salt": "seasoning",
    "black salt": "seasoning",
    # Vegetables
    "onion": "vegetable",
    "tomato": "vegetable",
    "potato": "vegetable",
    "carrot": "vegetable",
    "green bell pepper": "vegetable",
    "red bell pepper": "vegetable",
    "yellow bell pepper": "vegetable",
    "green beans": "vegetable",
    "green peas": "vegetable",
    "cabbage": "vegetable",
    "spinach": "vegetable",
    "broccoli": "vegetable",
    "cauliflower": "vegetable",
    "cucumber": "vegetable",
    "brinjal": "vegetable",
    "pumpkin": "vegetable",
    "beetroot": "vegetable",
    "bottle gourd": "vegetable",
    "bitter gourd": "vegetable",
    "radish": "vegetable",
    "bhindi": "vegetable",
    "drumstick": "vegetable",
    "zucchini": "vegetable",
    "capsicum": "vegetable",
    "spring onion": "vegetable",
    "shallot": "vegetable",
    "shallots": "vegetable",
    "sweet potato": "vegetable",
    "garlic": "vegetable",
    "ginger": "root",
    # Fruits
    "lemon": "fruit",
    "lemon juice": "fruit",
    "mango": "fruit",
    "banana": "fruit",
    "apple": "fruit",
    "pineapple": "fruit",
    "strawberries": "fruit",
    "orange": "fruit",
    "date": "fruit",
    "raisin": "dried fruit",
    "coconut": "fruit",
    # Herbs
    "mint leaf": "herb",
    "curry leaf": "herb",
    "basil": "herb",
    "fenugreek leaves": "herb",
    "oregano": "herb",
    "rosemary": "herb",
    "thyme": "herb",
    "dill": "herb",
    "parsley": "herb",
    # Dairy
    "milk": "dairy",
    "curd": "dairy",
    "ghee": "dairy",
    "butter": "dairy",
    "cream": "dairy",
    "paneer": "dairy",
    "cheese": "dairy",
    "mozzarella": "dairy",
    "parmesan": "dairy",
    "cheddar": "dairy",
    "feta": "dairy",
    "khoya": "dairy",
    "buttermilk": "dairy",
    "condensed milk": "dairy",
    "cream cheese": "dairy",
    # Oils
    "sunflower oil": "oil",
    "olive oil": "oil",
    "cooking oil": "oil",
    "coconut oil": "oil",
    "mustard oil": "oil",
    "sesame oil": "oil",
    # Pulses
    "toor dal": "pulse",
    "chana dal": "pulse",
    "moong dal": "pulse",
    "urad dal": "pulse",
    "masoor dal": "pulse",
    "rajma": "pulse",
    "chickpea": "pulse",
    "kala chana": "pulse",
    "green moong dal": "pulse",
    # Grains
    "rice": "grain",
    "semolina": "grain",
    "poha": "grain",
    "ragi": "grain",
    # Flours
    "all purpose flour": "flour",
    "whole wheat flour": "flour",
    "chickpea flour": "flour",
    "ragi flour": "flour",
    # Nuts
    "cashew": "nut",
    "almond": "nut",
    "pistachio": "nut",
    "walnut": "nut",
    "peanut": "nut",
    # Seeds
    "sesame": "seed",
    "poppy": "seed",
    "chia": "seed",
    # Meat / seafood
    "chicken": "meat",
    "mutton": "meat",
    "prawns": "seafood",
    # Egg / soy
    "egg": "egg",
    "tofu": "soy",
    # Condiments
    "soy sauce": "condiment",
    "vinegar": "condiment",
    "tamarind": "condiment",
    # Sweeteners
    "sugar": "sweetener",
    "brown sugar": "sweetener",
    "jaggery": "sweetener",
    "honey": "sweetener",
    # Baking
    "baking powder": "baking",
    "baking soda": "baking",
    "yeast": "baking",
    "vanilla": "flavoring",
    "cocoa": "baking",
    # Liquids
    "water": "liquid",
    # Pastes
    "ginger garlic": "paste",
}


# ---------------------------------------------------------
# DISPLAY NAME RULES
# ---------------------------------------------------------

DISPLAY_NAMES = {
    ("cumin", "seed"): "Cumin Seeds",
    ("cumin", "powder"): "Cumin Powder",
    ("coriander", "seed"): "Coriander Seeds",
    ("coriander", "powder"): "Coriander Powder",
    ("coriander", "leaf"): "Coriander Leaves",
    ("mustard", "seed"): "Mustard Seeds",
    ("mustard", "oil"): "Mustard Oil",
    ("fennel", "seed"): "Fennel Seeds",
    ("fenugreek", "seed"): "Fenugreek Seeds",
    ("black pepper", "powder"): "Black Pepper Powder",
    ("black pepper", "whole"): "Whole Black Peppercorns",
    ("turmeric", "powder"): "Turmeric Powder",
    ("red chilli", "powder"): "Red Chilli Powder",
    ("red chilli", "flakes"): "Red Chilli Flakes",
    ("red chilli", "dried"): "Dry Red Chilli",
    ("coconut", "fresh"): "Fresh Coconut",
    ("coconut", "milk"): "Coconut Milk",
    ("coconut", "oil"): "Coconut Oil",
    ("coconut", "desiccated"): "Desiccated Coconut",
    ("cardamom", "powder"): "Cardamom Powder",
    ("cardamom", "pod"): "Cardamom Pods",
    ("cinnamon", "stick"): "Cinnamon Stick",
    ("cinnamon", "powder"): "Cinnamon Powder",
    ("garam masala", "powder"): "Garam Masala Powder",
    ("ginger garlic", "paste"): "Ginger Garlic Paste",
    ("urad dal", "white"): "White Urad Dal",
    ("green peas", "fresh"): "Fresh Green Peas",
    ("cream", "fresh"): "Fresh Cream",
    ("tomato", "puree"): "Tomato Puree",
    ("peanut", "raw"): "Raw Peanuts",
    ("peanut", "roasted"): "Roasted Peanuts",
    ("banana", "ripe"): "Ripe Banana",
    ("chicken", "breast"): "Chicken Breast",
    ("egg", "whole"): "Whole Egg",
    ("saffron", "strand"): "Saffron Strands",
    ("olive oil", "default"): "Olive Oil",
    ("all purpose flour", "flour"): "All Purpose Flour",
    ("whole wheat flour", "flour"): "Whole Wheat Flour",
    ("chickpea flour", "flour"): "Chickpea Flour",
    ("rice", "flour"): "Rice Flour",
    ("corn", "flour"): "Corn Flour",
    ("kashmiri red chilli", "powder"): "Kashmiri Red Chilli Powder",
    ("chaat masala", "powder"): "Chaat Masala Powder",
    ("corn", "default"): "Corn",
    ("sesame", "seed"): "Sesame Seeds",
    ("sesame", "oil"): "Sesame Oil",
}


# ---------------------------------------------------------
# CATEGORY FUNCTION
# ---------------------------------------------------------


def get_category(canonical, form):

    canonical = str(canonical).strip().lower()

    form = str(form).strip().lower()

    # Form-specific overrides

    if canonical == "coconut" and form == "oil":
        return "oil"

    if canonical == "coconut" and form == "milk":
        return "dairy"

    if canonical == "coconut":
        return "fruit"

    if canonical == "sesame" and form == "oil":
        return "oil"

    if canonical == "coriander":
        if form in {"seed", "powder"}:
            return "spice"

        if form == "leaf":
            return "herb"

    if canonical == "mustard" and form == "oil":
        return "oil"

    if canonical == "red chilli":
        return "spice"

    if canonical == "corn" and form == "flour":
        return "flour"

    if canonical == "rice" and form == "flour":
        return "flour"

    if canonical == "cumin":
        return "spice"

    return CATEGORY_RULES.get(canonical, "other")


# ---------------------------------------------------------
# DISPLAY NAME FUNCTION
# ---------------------------------------------------------


def get_display_name(canonical, form):

    canonical = str(canonical).strip().lower()

    form = str(form).strip().lower()

    if (canonical, form) in DISPLAY_NAMES:
        return DISPLAY_NAMES[(canonical, form)]

    if form in {"", "default"}:
        return canonical.title()

    # Generic fallback.
    # Avoid awkward "Powder Cocoa" style names.

    return f"{canonical.title()} ({form.title()})"


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------


def main():

    if not MAPPING_FILE.exists():
        print(f"Input file not found: {MAPPING_FILE}")

        return

    df = pd.read_csv(MAPPING_FILE, dtype=str)

    required = [
        "candidate_ingredient",
        "final_canonical_ingredient",
        "final_ingredient_form",
        "final_mapping_status",
        "validation_status",
        "frequency",
    ]

    missing = [column for column in required if column not in df.columns]

    if missing:
        print("Missing required columns:", ", ".join(missing))

        return

    # -----------------------------------------------------
    # Normalize columns
    # -----------------------------------------------------

    for column in required:
        df[column] = df[column].fillna("").astype(str).str.strip()

    # -----------------------------------------------------
    # Keep validated automatic mappings
    # -----------------------------------------------------

    valid = df[
        (df["final_mapping_status"].str.upper() == "AUTO")
        & (df["validation_status"].isin(["VALID", "CORRECTED"]))
    ].copy()

    print("=" * 70)
    print("FINALIZING CANONICAL INGREDIENT DATABASE")
    print("=" * 70)

    print(f"\nValidated mapping rows: {len(valid)}")

    # -----------------------------------------------------
    # Numeric frequency
    # -----------------------------------------------------

    valid["frequency"] = pd.to_numeric(valid["frequency"], errors="coerce").fillna(0)

    # -----------------------------------------------------
    # Normalize canonical names
    # -----------------------------------------------------

    valid["canonical_name"] = (
        valid["final_canonical_ingredient"].str.lower().str.strip()
    )

    valid["ingredient_form"] = valid["final_ingredient_form"].str.lower().str.strip()

    # -----------------------------------------------------
    # Aggregate frequencies
    #
    # Same canonical ingredient + form can appear through
    # multiple candidate spellings.
    # -----------------------------------------------------

    grouped = valid.groupby(["canonical_name", "ingredient_form"], as_index=False).agg(
        recipe_occurrence_count=("frequency", "sum"),
        candidate_variant_count=("candidate_ingredient", "nunique"),
    )

    # -----------------------------------------------------
    # Create ingredient IDs
    # -----------------------------------------------------

    grouped = grouped.sort_values(["canonical_name", "ingredient_form"]).reset_index(
        drop=True
    )

    grouped["ingredient_id"] = [f"ING{i:05d}" for i in range(1, len(grouped) + 1)]

    # -----------------------------------------------------
    # Display names
    # -----------------------------------------------------

    grouped["display_name"] = grouped.apply(
        lambda row: get_display_name(row["canonical_name"], row["ingredient_form"]),
        axis=1,
    )

    # -----------------------------------------------------
    # Categories
    # -----------------------------------------------------

    grouped["category"] = grouped.apply(
        lambda row: get_category(row["canonical_name"], row["ingredient_form"]), axis=1
    )

    # -----------------------------------------------------
    # Metadata
    # -----------------------------------------------------

    grouped["source"] = "Indian recipe corpus + ingredient normalization pipeline"

    grouped["mapping_status"] = "VALIDATED_AUTO"

    # -----------------------------------------------------
    # Final column order
    # -----------------------------------------------------

    ingredients = grouped[
        [
            "ingredient_id",
            "canonical_name",
            "display_name",
            "ingredient_form",
            "category",
            "recipe_occurrence_count",
            "candidate_variant_count",
            "source",
            "mapping_status",
        ]
    ].copy()

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    ingredients.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    # -----------------------------------------------------
    # Statistics
    # -----------------------------------------------------

    print(f"\nUnique canonical ingredients: {len(ingredients)}")

    print(f"\nOutput: {OUTPUT_FILE}")

    print("\n" + "=" * 70)
    print("DATABASE SAMPLE")
    print("=" * 70)

    print(ingredients.head(100).to_string(index=False))

    print("\n" + "=" * 70)
    print("CATEGORY DISTRIBUTION")
    print("=" * 70)

    print(ingredients["category"].value_counts().to_string())

    print("\n" + "=" * 70)
    print("TOP INGREDIENTS BY OCCURRENCE")
    print("=" * 70)

    print(
        ingredients.sort_values("recipe_occurrence_count", ascending=False)
        .head(30)[
            [
                "ingredient_id",
                "display_name",
                "ingredient_form",
                "category",
                "recipe_occurrence_count",
                "candidate_variant_count",
            ]
        ]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
