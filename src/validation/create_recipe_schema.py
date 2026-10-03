import csv
from pathlib import Path


OUTPUT_FILE = Path("data/processed/recipes.csv")


FIELDS = [
    "recipe_id",
    "recipe_name",
    "name_local",
    "cuisine",
    "region",
    "meal_type",
    "category",
    "ingredients",
    "instructions",
    "prep_time_min",
    "cook_time_min",
    "total_time_min",
    "servings",
    "diet_type",
    "vegetarian",
    "vegan",
    "jain",
    "satvik",
    "contains",
    "calories_kcal",
    "protein_g",
    "carbs_g",
    "fat_g",
    "fiber_g",
    "source_id",
    "source_license",
]


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)

        writer.writeheader()

    print(f"Recipe schema created: {OUTPUT_FILE}")
    print(f"Fields: {len(FIELDS)}")


if __name__ == "__main__":
    main()
