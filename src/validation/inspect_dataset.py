import json
from pathlib import Path


DATA_DIR = Path("data/raw/indian_foods")


def inspect_json_file(file_path: Path):
    print("=" * 60)
    print(f"FILE: {file_path}")
    print("=" * 60)

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    print("\nTop-level fields:")
    for key in data:
        print(f"  - {key}")

    print("\nBasic information:")

    print(f"  ID: {data.get('id')}")
    print(f"  Name: {data.get('name_en')}")
    print(f"  Region: {data.get('region')}")
    print(f"  Category: {data.get('category')}")
    print(f"  Vegetarian: {data.get('veg')}")

    print("\nServing:")
    print(f"  Unit: {data.get('serving_unit')}")
    print(f"  Weight: {data.get('serving_grams_default')} g")

    print("\nNutrition per 100g:")

    macros = data.get("macros_per_100g", {})

    for key, value in macros.items():
        print(f"  {key}: {value}")

    print("\nIngredients:")
    print(f"  {data.get('ingredients_summary')}")

    print("\nDietary information:")
    print(f"  Jain: {data.get('jain')}")
    print(f"  Satvik: {data.get('satvik')}")

    print("\nContains:")
    for item in data.get("contains", []):
        print(f"  - {item}")

    print("\nSources:")
    for source in data.get("sources", []):
        print(f"  - {source}")

    print("\nConfidence:")
    print(f"  {data.get('confidence')}/10")

    print("\nLast verified:")
    print(f"  {data.get('last_verified')}")

    print("\nNotes:")
    print(f"  {data.get('notes')}")

    print()


def main():
    files = list(DATA_DIR.glob("*.json"))

    if not files:
        print(f"No JSON files found in: {DATA_DIR}")
        return

    print(f"Found {len(files)} JSON file(s).\n")

    for file_path in files:
        inspect_json_file(file_path)


if __name__ == "__main__":
    main()
