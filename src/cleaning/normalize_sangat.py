import json
import csv
from pathlib import Path


RAW_DIR = Path("data/raw/indian_foods")
OUTPUT_DIR = Path("data/processed")

OUTPUT_FILE = OUTPUT_DIR / "indian_foods.csv"


def normalize_dish(data):
    macros = data.get("macros_per_100g", {})

    return {
        "recipe_id": data.get("id"),
        "recipe_name": data.get("name_en"),
        "name_hi": data.get("name_hi", ""),
        "region": data.get("region"),
        "category": data.get("category"),
        "serving_unit": data.get("serving_unit"),
        "serving_grams": data.get("serving_grams_default"),
        "calories_kcal_100g": macros.get("kcal"),
        "protein_g_100g": macros.get("protein_g"),
        "carbs_g_100g": macros.get("carbs_g"),
        "fat_g_100g": macros.get("fat_g"),
        "fiber_g_100g": macros.get("fiber_g"),
        "ingredients": data.get("ingredients_summary", ""),
        "vegetarian": data.get("veg", False),
        "jain": data.get("jain", False),
        "satvik": data.get("satvik", False),
        "contains": ", ".join(data.get("contains", [])),
        "source": "; ".join(data.get("sources", [])),
        "confidence": data.get("confidence"),
        "last_verified": data.get("last_verified"),
        "notes": data.get("notes", ""),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    records = []

    json_files = list(RAW_DIR.glob("*.json"))

    if not json_files:
        print("No JSON files found.")
        return

    for file_path in json_files:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        normalized = normalize_dish(data)
        records.append(normalized)

    fieldnames = records[0].keys()

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(records)

    print(f"Processed {len(records)} dish(es).")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
