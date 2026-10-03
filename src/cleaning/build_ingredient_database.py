import pandas as pd
from pathlib import Path


# ---------------------------------------------------------
# FILES
# ---------------------------------------------------------

INPUT_FILE = Path("data/mappings/final_ingredient_mapping_validated.csv")

OUTPUT_FILE = Path("data/processed/ingredients.csv")


# ---------------------------------------------------------
# INGREDIENT CATEGORIES
# ---------------------------------------------------------

CATEGORY_RULES = {
    # Seasonings
    "salt": "seasoning",
    "black salt": "seasoning",
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
    "radish": "vegetable",
    "bhindi": "vegetable",
    "drumstick": "vegetable",
    "zucchini": "vegetable",
    "capsicum": "vegetable",
    "spring onion": "vegetable",
    "shallot": "vegetable",
    "shallots": "vegetable",
    "sweet potato": "vegetable",
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
    "coriander": "herb",
    "mint": "herb",
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
    "wheat": "grain",
    "semolina": "grain",
    "poha": "grain",
    "ragi": "grain",
    # Flours
    "all purpose flour": "flour",
    "whole wheat flour": "flour",
    "chickpea flour": "flour",
    "rice": "grain",
    "corn": "grain",
    "ragi flour": "flour",
    # Nuts / seeds
    "cashew": "nut",
    "almond": "nut",
    "pistachio": "nut",
    "walnut": "nut",
    "peanut": "nut",
    "sesame": "seed",
    "poppy": "seed",
    "chia": "seed",
    # Protein
    "egg": "egg",
    "chicken": "meat",
    "mutton": "meat",
    "prawns": "seafood",
    "tofu": "soy",
    # Sauces / condiments
    "soy sauce": "condiment",
    "vinegar": "condiment",
    "red chilli": "spice",
    "tamarind": "condiment",
    "tomato": "vegetable",
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
    # Other
    "water": "liquid",
    "ginger": "root",
    "garlic": "vegetable",
    "ginger garlic": "paste",
}


# ---------------------------------------------------------
# DISPLAY NAME
# ---------------------------------------------------------


def create_display_name(canonical, form):
    """
    Create a human-readable ingredient name.
    """

    canonical = str(canonical).strip()
    form = str(form).strip()

    if not canonical:
        return ""

    if form == "default":
        return canonical.title()

    special_names = {
        ("cumin", "seed"): "Cumin Seeds",
        ("cumin", "powder"): "Cumin Powder",
        ("coriander", "seed"): "Coriander Seeds",
        ("coriander", "powder"): "Coriander Powder",
        ("coriander", "leaf"): "Coriander Leaves",
        ("mustard", "seed"): "Mustard Seeds",
        ("mustard", "oil"): "Mustard Oil",
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
    }

    if (canonical, form) in special_names:
        return special_names[(canonical, form)]

    return f"{form.title()} {canonical.title()}"


# ---------------------------------------------------------
# CATEGORY
# ---------------------------------------------------------


def get_category(canonical):
    """
    Assign a broad ingredient category.
    """

    canonical = str(canonical).strip().lower()

    return CATEGORY_RULES.get(canonical, "other")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------


def main():

    if not INPUT_FILE.exists():
        print(f"Input file not found: {INPUT_FILE}")
        return

    df = pd.read_csv(INPUT_FILE, dtype=str)

    required_columns = [
        "candidate_ingredient",
        "final_canonical_ingredient",
        "final_ingredient_form",
        "final_mapping_status",
        "validation_status",
        "frequency",
    ]

    missing = [column for column in required_columns if column not in df.columns]

    if missing:
        print("Missing required columns:", ", ".join(missing))
        return

    # -----------------------------------------------------
    # Normalize text
    # -----------------------------------------------------

    for column in required_columns:
        df[column] = df[column].fillna("").astype(str).str.strip()

    # -----------------------------------------------------
    # Keep only validated/corrected AUTO mappings
    # -----------------------------------------------------

    valid = df[
        (df["final_mapping_status"].str.upper() == "AUTO")
        & (df["validation_status"].isin(["VALID", "CORRECTED"]))
    ].copy()

    print("=" * 70)
    print("BUILDING CANONICAL INGREDIENT DATABASE")
    print("=" * 70)

    print(f"\nTotal mapping records: {len(df)}")

    print(f"Validated automatic mappings: {len(valid)}")

    # -----------------------------------------------------
    # Remove duplicates
    #
    # Same canonical ingredient + form =
    # one canonical database record.
    # -----------------------------------------------------

    valid["canonical_key"] = (
        valid["final_canonical_ingredient"].str.lower().str.strip()
        + "|"
        + valid["final_ingredient_form"].str.lower().str.strip()
    )

    unique = (
        valid.sort_values("frequency", ascending=False)
        .drop_duplicates(subset=["canonical_key"], keep="first")
        .copy()
    )

    # -----------------------------------------------------
    # Create IDs
    # -----------------------------------------------------

    unique = unique.reset_index(drop=True)

    unique["ingredient_id"] = [f"ING{i:05d}" for i in range(1, len(unique) + 1)]

    # -----------------------------------------------------
    # Canonical name
    # -----------------------------------------------------

    unique["canonical_name"] = (
        unique["final_canonical_ingredient"].str.lower().str.strip()
    )

    # -----------------------------------------------------
    # Ingredient form
    # -----------------------------------------------------

    unique["ingredient_form"] = unique["final_ingredient_form"].str.lower().str.strip()

    # -----------------------------------------------------
    # Display name
    # -----------------------------------------------------

    unique["display_name"] = unique.apply(
        lambda row: create_display_name(row["canonical_name"], row["ingredient_form"]),
        axis=1,
    )

    # -----------------------------------------------------
    # Category
    # -----------------------------------------------------

    unique["category"] = unique["canonical_name"].apply(get_category)

    # -----------------------------------------------------
    # Frequency
    # -----------------------------------------------------

    unique["recipe_occurrence_count"] = (
        pd.to_numeric(unique["frequency"], errors="coerce").fillna(0).astype(int)
    )

    # -----------------------------------------------------
    # Source
    # -----------------------------------------------------

    unique["source"] = "Indian recipe corpus + ingredient normalization pipeline"

    # -----------------------------------------------------
    # Mapping status
    # -----------------------------------------------------

    unique["mapping_status"] = "VALIDATED_AUTO"

    # -----------------------------------------------------
    # Select final columns
    # -----------------------------------------------------

    ingredients = unique[
        [
            "ingredient_id",
            "canonical_name",
            "display_name",
            "ingredient_form",
            "category",
            "recipe_occurrence_count",
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
    print("INGREDIENT DATABASE SAMPLE")
    print("=" * 70)

    print(ingredients.head(100).to_string(index=False))

    print("\n" + "=" * 70)
    print("CATEGORY DISTRIBUTION")
    print("=" * 70)

    print(ingredients["category"].value_counts().to_string())


if __name__ == "__main__":
    main()
