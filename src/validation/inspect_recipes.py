import pandas as pd
from pathlib import Path


DATA_FILE = Path("data/raw/recipes/indian_recipes_raw.csv")


def main():
    if not DATA_FILE.exists():
        print(f"Dataset not found: {DATA_FILE}")
        return

    df = pd.read_csv(DATA_FILE)

    print("=" * 70)
    print("KITCHENPILOT-V1 RECIPE DATASET INSPECTION")
    print("=" * 70)

    print(f"\nDataset file:")
    print(f"  {DATA_FILE}")

    print(f"\nNumber of recipes:")
    print(f"  {len(df)}")

    print(f"\nNumber of columns:")
    print(f"  {len(df.columns)}")

    print("\nColumns:")
    for column in df.columns:
        print(f"  - {column}")

    print("\nData types:")
    print(df.dtypes)

    print("\nMissing values:")
    missing = df.isnull().sum()

    for column, count in missing.items():
        print(f"  {column}: {count}")

    print("\nDuplicate rows:")
    print(f"  {df.duplicated().sum()}")

    print("\nSample recipes:")

    columns_to_show = [
        column
        for column in [
            "RecipeName",
            "TranslatedRecipeName",
            "Cuisine",
            "Course",
            "Diet",
        ]
        if column in df.columns
    ]

    if columns_to_show:
        print(df[columns_to_show].head(10).to_string(index=False))

    if "Cuisine" in df.columns:
        print("\nCuisine distribution:")
        print(df["Cuisine"].value_counts().head(20))

    if "Course" in df.columns:
        print("\nCourse distribution:")
        print(df["Course"].value_counts().head(20))

    if "Diet" in df.columns:
        print("\nDiet distribution:")
        print(df["Diet"].value_counts().head(20))

    print("\nInspection complete.")


if __name__ == "__main__":
    main()
