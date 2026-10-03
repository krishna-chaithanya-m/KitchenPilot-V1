"""Generate review-only candidate links from KitchenPilot ingredients to CNF."""

import re
import time
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INGREDIENTS_FILE = (
    Path("data/processed/ingredients.csv")
    if Path("data/processed/ingredients.csv").is_file()
    else PROJECT_ROOT / "data/processed/ingredients.csv"
)
CNF_FILE = (
    Path("data/processed/cnf_2026_nutrition.csv")
    if Path("data/processed/cnf_2026_nutrition.csv").is_file()
    else PROJECT_ROOT / "data/processed/cnf_2026_nutrition.csv"
)
VALIDATED_MAPPING_FILE = (
    Path("data/mappings/final_ingredient_mapping_validated.csv")
    if Path("data/mappings/final_ingredient_mapping_validated.csv").is_file()
    else PROJECT_ROOT / "data/mappings/final_ingredient_mapping_validated.csv"
)
LINKED_RECIPE_INGREDIENTS_FILE = (
    Path("data/processed/recipe_ingredients_linked.csv")
    if Path("data/processed/recipe_ingredients_linked.csv").is_file()
    else PROJECT_ROOT / "data/processed/recipe_ingredients_linked.csv"
)
OUTPUT_FILE = (
    Path("data/mappings/cnf_ingredient_mapping_review.csv")
    if Path("data/mappings").is_dir()
    else PROJECT_ROOT / "data/mappings/cnf_ingredient_mapping_review.csv"
)

CNF_SOURCE = "CNF_2026"
MAX_CANDIDATES_PER_INGREDIENT = 10
MIN_FUZZY_SCORE = 0.72
FUZZY_FILL_LIMIT = 3
FUZZY_MIN_QUERY_LENGTH = 6
ALTERNATE_ALIAS_SOURCE_CODES = {
    "0",
    "1",
    "3",
    "4",
    "9",
    "10",
    "11",
    "20",
    "23",
    "28",
}
COMPOSITE_FOOD_PREFIXES = (
    "bagel",
    "bagels",
    "beverage",
    "beverages",
    "plant-based beverage",
    "carbonated drink",
    "soft drink",
    "drink",
    "drinks",
    "milkshake",
    "milkshakes",
    "frozen entree",
    "bar",
    "bars",
    "pizza",
    "pasta",
    "noodles",
    "soup",
    "soups",
    "sandwich",
    "bread",
    "cookie",
    "cookies",
    "cracker",
    "crackers",
    "cake",
    "cakes",
    "cereal, ready to eat",
    "cereal, infant",
    "rice, cheese",
    "rice crackers",
    "rice, spanish",
    "rice mix",
    "rice and vermicelli mix",
    "snack",
    "snacks",
    "fast food",
    "salad",
    "sauce",
    "sauces",
    "pie",
    "dessert",
    "desserts",
    "candy",
    "candies",
    "babyfood",
    "baby food",
    "entree",
    "entrees",
    "meal",
    "meals",
    "tortilla",
    "tortillas",
    "dulce de leche",
    "margarine",
    "margarine-like spread",
)

REQUIRED_INGREDIENT_COLUMNS = [
    "ingredient_id",
    "canonical_name",
    "display_name",
    "ingredient_form",
    "category",
]
REQUIRED_CNF_COLUMNS = [
    "source_food_id",
    "food_name",
    "food_description",
    "food_form",
    "alternate_names_en",
    "food_source_code",
    "source_usda_ndb_code",
    "source_reference",
    "source_food_last_updated_date",
    "license",
]
REQUIRED_MAPPING_COLUMNS = [
    "candidate_ingredient",
    "cleaned_candidate",
    "normalized_candidate",
    "final_canonical_ingredient",
    "final_ingredient_form",
    "validation_status",
]

OUTPUT_COLUMNS = [
    "ingredient_id",
    "canonical_name",
    "display_name",
    "ingredient_form",
    "category",
    "cnf_food_code",
    "cnf_food_name",
    "cnf_food_description",
    "cnf_alternate_description",
    "cnf_food_form",
    "match_method",
    "match_score",
    "candidate_rank",
    "selection_status",
    "review_notes",
    "matched_term",
    "cnf_food_source_code",
    "source_usda_ndb_code",
    "source_reference",
    "cnf_food_last_updated_date",
    "recipe_form_evidence",
]

FORM_ALIASES = {
    "powder": {"powder", "powdered", "ground"},
    "seed": {"seed", "seeds"},
    "leaf": {"leaf", "leaves"},
    "dried": {"dry", "dried", "dehydrated"},
    "dry": {"dry", "dried", "dehydrated"},
    "oil": {"oil"},
    "flour": {"flour"},
    "fresh": {"fresh"},
    "white": {"white"},
    "basmati": {"basmati"},
    "whole": {"whole"},
    "paste": {"paste"},
    "kabuli": {"kabuli", "garbanzo"},
    "ripe": {"ripe"},
    "roasted": {"roasted"},
    "flakes": {"flake", "flakes"},
    "pod": {"pod", "pods"},
    "stick": {"stick", "sticks"},
    "strand": {"strand", "strands"},
    "puree": {"puree"},
    "juice": {"juice"},
    "sauce": {"sauce"},
    "desiccated": {"desiccated"},
    "hung": {"hung"},
    "caster": {"caster"},
    "active dry": {"active", "dry"},
    "red": {"red"},
    "green": {"green"},
    "orange": {"orange"},
    "yellow": {"yellow"},
}

CNF_FORM_TERMS = (
    "raw",
    "cooked",
    "boiled",
    "dry",
    "dried",
    "dehydrated",
    "powder",
    "powdered",
    "ground",
    "seed",
    "seeds",
    "leaf",
    "leaves",
    "oil",
    "flour",
    "paste",
    "whole",
    "white",
    "brown",
    "basmati",
    "wild",
    "glutinous",
    "parboiled",
    "regular",
    "long grain",
    "medium grain",
    "short grain",
    "green",
    "orange",
    "yellow",
    "fresh",
    "roasted",
    "fried",
    "flakes",
    "pod",
    "pods",
    "stick",
    "sticks",
    "split",
    "mature",
    "skim",
    "salted",
    "unsalted",
    "instant",
    "puree",
    "juice",
    "sauce",
    "desiccated",
    "ketchup",
    "catsup",
    "buttermilk",
    "sweetened",
    "chocolate",
    "condensed",
    "evaporated",
    "fortified",
    "pasteurized",
    "homogenized",
    "human",
    "goat",
    "sheep",
    "strawberry",
    "flavoured",
    "flavored",
)

DISTINCT_FORM_CUES = set(CNF_FORM_TERMS) | {
    "puree",
    "juice",
    "sauce",
    "skim",
    "salted",
    "unsalted",
    "instant",
}
DEFAULT_FORM_PENALTY_CUES = {
    "powder",
    "powdered",
    "ground",
    "seed",
    "seeds",
    "leaf",
    "leaves",
    "oil",
    "flour",
    "paste",
    "whole",
    "white",
    "brown",
    "basmati",
    "fresh",
    "flakes",
    "pod",
    "pods",
    "puree",
    "juice",
    "sauce",
    "desiccated",
    "green",
    "orange",
    "yellow",
    "chocolate",
    "goat",
    "sheep",
    "human",
    "coconut",
    "buttermilk",
    "condensed",
    "sweetened",
    "skim",
    "pasteurized",
    "homogenized",
    "canned",
    "fortified",
    "strawberry",
    "flavoured",
    "flavored",
}
SPECIALIZED_GRAIN_CUES = {
    "brown",
    "glutinous",
    "wild",
    "parboiled",
    "instant",
    "basmati",
}
REGULAR_GRAIN_CUES = {"regular", "long grain"}

PREPARATION_STATES = {
    "raw": re.compile(r"\b(?:raw|uncooked)\b", re.IGNORECASE),
    "dry": re.compile(r"\b(?:dry|dried|dehydrated)\b", re.IGNORECASE),
    "cooked": re.compile(
        r"\b(?:cooked|prepared|steamed|fried|roasted)\b", re.IGNORECASE
    ),
    "boiled": re.compile(r"\bboiled\b", re.IGNORECASE),
}

METHOD_PRIORITY = {
    "EXACT_NAME": 0,
    "ALIAS_MATCH": 1,
    "FORM_MATCH": 2,
    "TOKEN_MATCH": 3,
    "FUZZY_CANDIDATE": 4,
}
TOKEN_REPLACEMENTS = {
    "tomatoes": "tomato",
    "potatoes": "potato",
    "onions": "onion",
    "leaves": "leaf",
    "seeds": "seed",
    "beans": "bean",
    "peas": "pea",
    "spices": "spice",
    "chilli": "chili",
    "chillies": "chili",
    "chile": "chili",
    "chiles": "chili",
    "berries": "berry",
    "moong": "mung",
    "almonds": "almond",
    "peppers": "pepper",
    "mushrooms": "mushroom",
    "carrots": "carrot",
    "apples": "apple",
    "bananas": "banana",
    "lemons": "lemon",
    "mangos": "mango",
    "mangoes": "mango",
    "eggs": "egg",
    "noodles": "noodle",
    "crackers": "cracker",
    "flakes": "flake",
    "peppercorns": "peppercorn",
    "grains": "grain",
    "nuts": "nut",
    "chickpeas": "chickpea",
}
MATCH_STOPWORDS = {"dal", "year", "round", "average", "style", "type", "stages"}

DERIVED_FOOD_TERMS = {
    "butter",
    "meal",
    "paste",
    "powder",
    "powdered",
    "flour",
    "noodles",
    "noodle",
    "cereal",
    "cereals",
    "crackers",
    "cracker",
    "chips",
    "chip",
    "ketchup",
    "catsup",
    "puree",
    "sauce",
    "sauces",
    "juice",
    "juices",
    "oil",
    "oils",
    "syrup",
    "syrups",
    "milk",
    "extract",
    "flakes",
    "flake",
    "dehydrated",
    "dried",
    "dry",
    "mix",
    "sprouted",
    "sprouts",
}

BROAD_CNF_CATEGORIES = {
    "nut",
    "nuts",
    "grain",
    "grains",
    "spice",
    "spices",
    "bean",
    "beans",
    "legume",
    "legumes",
    "pea",
    "peas",
    "vegetable",
    "vegetables",
    "fruit",
    "fruits",
    "seed",
    "seeds",
    "fat",
    "fats",
    "oil",
    "oils",
    "cereal",
    "cereals",
    "candy",
    "candies",
    "beverage",
    "beverages",
    "poultry",
    "meat",
    "finfish",
    "shellfish",
    "dairy",
    "soup",
    "sauce",
    "babyfood",
    "snack",
    "snacks",
    "dessert",
}


def normalize_text(value: Any) -> str:
    """Normalize case and punctuation while retaining words inside parentheses."""
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    tokens = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
    normalized_tokens = [TOKEN_REPLACEMENTS.get(token, token) for token in tokens]
    return " ".join(normalized_tokens)


def split_aliases(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [part.strip() for part in re.split(r"[;,|]", str(value)) if part.strip()]


def _require_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: {', '.join(missing)}")


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required_paths = (INGREDIENTS_FILE, CNF_FILE, VALIDATED_MAPPING_FILE)
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Required input file(s) not found: " + ", ".join(missing)
        )

    read_options = {
        "dtype": "string",
        "keep_default_na": False,
        "encoding": "utf-8-sig",
    }
    ingredients = pd.read_csv(INGREDIENTS_FILE, **read_options)
    cnf_rows = pd.read_csv(
        CNF_FILE, usecols=REQUIRED_CNF_COLUMNS, low_memory=False, **read_options
    )
    mappings = pd.read_csv(VALIDATED_MAPPING_FILE, **read_options)

    _require_columns(ingredients, REQUIRED_INGREDIENT_COLUMNS, str(INGREDIENTS_FILE))
    _require_columns(cnf_rows, REQUIRED_CNF_COLUMNS, str(CNF_FILE))
    _require_columns(mappings, REQUIRED_MAPPING_COLUMNS, str(VALIDATED_MAPPING_FILE))

    if not LINKED_RECIPE_INGREDIENTS_FILE.is_file():
        recipe_evidence = pd.DataFrame(
            columns=["ingredient_id", "ingredient", "preparation"]
        )
    else:
        recipe_evidence = pd.read_csv(
            LINKED_RECIPE_INGREDIENTS_FILE,
            usecols=["ingredient_id", "ingredient", "preparation"],
            dtype="string",
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    return ingredients, cnf_rows, mappings, recipe_evidence


def _is_composite_food(food_name: str) -> bool:
    normalized = normalize_text(food_name)
    return any(
        normalized.startswith(normalize_text(prefix))
        for prefix in COMPOSITE_FOOD_PREFIXES
    )


def _unique_cnf_foods(cnf_rows: pd.DataFrame) -> list[dict[str, Any]]:
    metadata_columns = [
        column for column in REQUIRED_CNF_COLUMNS if column != "source_food_id"
    ]
    variation = cnf_rows.groupby("source_food_id", dropna=False)[
        metadata_columns
    ].nunique(dropna=False)
    if variation.gt(1).any(axis=None):
        raise ValueError("CNF food metadata varies across nutrient rows for a food ID")

    foods = cnf_rows.drop_duplicates("source_food_id", keep="first")
    foods = foods[~foods["food_name"].map(_is_composite_food)]
    foods = foods.sort_values(
        by="source_food_id",
        key=lambda values: pd.to_numeric(values, errors="coerce"),
        kind="stable",
    )
    records: list[dict[str, Any]] = []
    for row in foods.to_dict(orient="records"):
        name = row["food_name"]
        alternate_terms = (
            split_aliases(row["alternate_names_en"])
            if row["food_source_code"] in ALTERNATE_ALIAS_SOURCE_CODES
            else []
        )
        description = row["food_description"]
        form_source_text = re.sub(r"\([^)]*\)", "", name)
        form_tokens = set(normalize_text(form_source_text).split())
        embedded_forms = [
            form
            for form in CNF_FORM_TERMS
            if re.search(rf"\b{re.escape(form)}\b", form_source_text.casefold())
        ]
        existing_tags = [
            tag.strip()
            for tag in row["food_form"].split(";")
            if tag.strip() and tag.strip() != "unspecified_in_description"
        ]
        cnf_form = ";".join(dict.fromkeys([*existing_tags, *embedded_forms]))
        cnf_form = cnf_form or "unspecified_in_description"

        segs = [part.strip() for part in name.split(",") if part.strip()]
        idx = 0
        while idx < len(segs) - 1 and normalize_text(segs[idx]) in BROAD_CNF_CATEGORIES:
            idx += 1
        primary_segment = segs[idx] if idx < len(segs) else (segs[0] if segs else "")
        primary_tokens = set(normalize_text(primary_segment).split()) - MATCH_STOPWORDS

        records.append(
            {
                **row,
                "name_normalized": normalize_text(name),
                "alternate_terms": alternate_terms,
                "alternate_normalized": [
                    normalize_text(term) for term in alternate_terms
                ],
                "all_normalized_terms": [
                    normalize_text(name),
                    *[normalize_text(term) for term in alternate_terms],
                ],
                "tokens": form_tokens,
                "primary_segment": primary_segment,
                "primary_tokens": primary_tokens,
                "cnf_form": cnf_form,
                "form_tokens": (
                    set()
                    if cnf_form == "unspecified_in_description"
                    else set(cnf_form.split(";"))
                ),
                "description_for_review": description,
            }
        )
    return records


def _build_cnf_index(foods: list[dict[str, Any]]) -> dict[str, Any]:
    exact_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    alternate_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    token_to_food_ids: dict[str, set[str]] = defaultdict(set)

    for food in foods:
        fid = food["source_food_id"]
        exact_index[food["name_normalized"]].append(food)
        for alt in food["alternate_normalized"]:
            alternate_index[alt].append(food)
        for phrase in food["all_normalized_terms"]:
            for token in phrase.split():
                if token not in MATCH_STOPWORDS and len(token) > 1:
                    token_to_food_ids[token].add(fid)

    return {
        "exact": exact_index,
        "alternate": alternate_index,
        "tokens": token_to_food_ids,
    }


def _validated_aliases(
    mappings: pd.DataFrame, ingredients: pd.DataFrame
) -> dict[str, list[tuple[str, str]]]:
    canonical_forms = {
        (
            normalize_text(row.canonical_name),
            normalize_text(row.ingredient_form),
        ): row.ingredient_id
        for row in ingredients.itertuples(index=False)
    }
    aliases: dict[str, list[tuple[str, str]]] = defaultdict(list)
    valid_rows = mappings[
        mappings.validation_status.str.strip().str.casefold().eq("valid")
    ]
    for row in valid_rows.to_dict(orient="records"):
        key = (
            normalize_text(row["final_canonical_ingredient"]),
            normalize_text(row["final_ingredient_form"]),
        )
        ingredient_id = canonical_forms.get(key)
        if ingredient_id is None:
            continue
        for column in (
            "candidate_ingredient",
            "cleaned_candidate",
            "normalized_candidate",
        ):
            term = str(row[column]).strip()
            if term and all(
                normalize_text(existing[0]) != normalize_text(term)
                for existing in aliases[ingredient_id]
            ):
                aliases[ingredient_id].append((term, f"validated:{column}"))
    return aliases


def _recipe_form_evidence(evidence: pd.DataFrame, ingredient_id: str) -> dict[str, int]:
    counts = {state: 0 for state in ("raw", "dry", "cooked", "boiled", "unspecified")}
    rows = evidence[evidence["ingredient_id"].eq(ingredient_id)]
    for row in rows.to_dict(orient="records"):
        text = f"{row.get('ingredient', '')} {row.get('preparation', '')}"
        matched = [
            state
            for state, pattern in PREPARATION_STATES.items()
            if pattern.search(text)
        ]
        if not matched:
            counts["unspecified"] += 1
        else:
            for state in matched:
                counts[state] += 1
    return counts


def _evidence_label(counts: dict[str, int]) -> str:
    return ";".join(f"{state}={counts[state]}" for state in counts)


def _query_terms(
    ingredient: dict[str, Any], aliases: list[tuple[str, str]]
) -> list[dict[str, str]]:
    terms: dict[str, dict[str, str]] = {}
    values = [(ingredient["display_name"], "display_name"), *aliases]
    values.append((ingredient["canonical_name"], "canonical_name"))
    for value, kind in values:
        normalized = normalize_text(value)
        if normalized:
            terms.setdefault(normalized, {"term": value, "kind": kind})
    form = normalize_text(ingredient["ingredient_form"])
    if form not in {"", "default"}:
        for suffix in sorted(FORM_ALIASES.get(form, {form})):
            value = f"{ingredient['canonical_name']} {suffix}"
            normalized = normalize_text(value)
            if normalized:
                terms.setdefault(normalized, {"term": value, "kind": "form_alias"})
    return list(terms.values())


def _token_match_score(query: str, food: dict[str, Any]) -> float:
    query_tokens = set(normalize_text(query).split()) - MATCH_STOPWORDS
    if not query_tokens:
        return 0.0

    best = 0.0
    for phrase in food["all_normalized_terms"]:
        phrase_tokens = set(phrase.split()) - MATCH_STOPWORDS
        overlap = query_tokens & phrase_tokens
        if not overlap:
            continue
        if len(query_tokens) == 1:
            if phrase != food["name_normalized"] and phrase_tokens != query_tokens:
                continue
            if (
                not (overlap & food["primary_tokens"])
                and phrase_tokens != query_tokens
            ):
                continue
        coverage = len(overlap) / len(query_tokens)
        if coverage < 0.65:
            continue
        jaccard = len(overlap) / len(query_tokens | phrase_tokens)
        best = max(best, 0.55 * coverage + 0.45 * jaccard)
    return best


def _form_signal(ingredient_form: str, food: dict[str, Any]) -> str:
    form = normalize_text(ingredient_form)
    if not form or form == "default":
        return "UNSPECIFIED"
    expected = FORM_ALIASES.get(form, {form})
    if expected & food["form_tokens"]:
        return "MATCH"
    if form in food["tokens"]:
        return "MATCH"
    if expected & set(food["name_normalized"].split()):
        return "MATCH"
    if food["form_tokens"]:
        return "CONFLICT"
    return "UNVERIFIED"


def _form_compatibility_priority(form_signal: str) -> int:
    if form_signal == "MATCH":
        return 0
    if form_signal in {"UNSPECIFIED", "UNVERIFIED"}:
        return 1
    return 2


def _best_candidate_match(
    query_terms: list[dict[str, str]], food: dict[str, Any]
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for query in query_terms:
        term = query["term"]
        normalized = normalize_text(term)
        if not normalized:
            continue

        if normalized == food["name_normalized"]:
            if query["kind"] == "form_alias":
                method = "FORM_MATCH"
                score = 0.96
            else:
                method = (
                    "ALIAS_MATCH"
                    if query["kind"].startswith("validated:")
                    else "EXACT_NAME"
                )
                score = 1.0 if method == "EXACT_NAME" else 0.97
        elif normalized in food["alternate_normalized"]:
            method = "ALIAS_MATCH"
            score = 0.96
        else:
            score = _token_match_score(term, food)
            if score >= 0.35:
                method = "TOKEN_MATCH"
            else:
                continue

        choice = {
            "base_method": method,
            "score": score,
            "matched_term": term,
            "term_kind": query["kind"],
        }
        if best is None or (METHOD_PRIORITY[method], -score, normalize_text(term)) < (
            METHOD_PRIORITY[best["base_method"]],
            -best["score"],
            normalize_text(best["matched_term"]),
        ):
            best = choice
    return best


def _fuzzy_candidates(
    query_terms: list[dict[str, str]],
    foods: list[dict[str, Any]],
    existing_codes: set[str],
) -> list[tuple[str, dict[str, Any]]]:
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for food in foods:
        if food["source_food_id"] in existing_codes:
            continue
        best_ratio = 0.0
        best_term = ""
        for query in query_terms[:8]:
            normalized = normalize_text(query["term"])
            if len(normalized.replace(" ", "")) < FUZZY_MIN_QUERY_LENGTH:
                continue
            query_tokens = set(normalized.split()) - MATCH_STOPWORDS
            if not query_tokens:
                continue
            for phrase in food["all_normalized_terms"]:
                phrase_tokens = set(phrase.split()) - MATCH_STOPWORDS
                token_overlap = len(query_tokens & phrase_tokens) / len(query_tokens)
                if token_overlap < 0.65:
                    continue
                ratio = SequenceMatcher(
                    None, normalized, phrase, autojunk=False
                ).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_term = query["term"]
        if best_ratio >= MIN_FUZZY_SCORE:
            scored.append(
                (
                    best_ratio,
                    food["source_food_id"],
                    {
                        "base_method": "FUZZY_CANDIDATE",
                        "score": best_ratio,
                        "matched_term": best_term,
                        "term_kind": "fuzzy",
                    },
                )
            )
    scored.sort(
        key=lambda item: (-item[0], int(item[1]) if item[1].isdigit() else item[1])
    )
    return [(food_id, match) for _, food_id, match in scored[:FUZZY_FILL_LIMIT]]


def _is_dry_form(food: dict[str, Any]) -> bool:
    return bool({"dry", "dried", "dehydrated", "raw"} & food["form_tokens"])


def _is_primary_identity(
    ingredient: dict[str, Any], food: dict[str, Any], aliases: list[tuple[str, str]]
) -> bool:
    canonical_tokens = set(normalize_text(ingredient["canonical_name"]).split()) - MATCH_STOPWORDS
    display_tokens = set(normalize_text(ingredient["display_name"]).split()) - MATCH_STOPWORDS
    alias_tokens = set()
    for term, _ in aliases:
        alias_tokens.update(set(normalize_text(term).split()) - MATCH_STOPWORDS)
    query_tokens = canonical_tokens | display_tokens | alias_tokens
    if query_tokens & food["primary_tokens"]:
        return True
    return False


def _derived_form_penalty(ingredient: dict[str, Any], food: dict[str, Any]) -> int:
    canonical_tokens = set(normalize_text(ingredient["canonical_name"]).split())
    display_tokens = set(normalize_text(ingredient["display_name"]).split())
    form = normalize_text(ingredient["ingredient_form"])
    expected_forms = FORM_ALIASES.get(form, {form}) if form not in {"", "default"} else set()
    allowed = canonical_tokens | display_tokens | expected_forms

    if normalize_text(ingredient["category"]) == "dairy":
        allowed.update({"milk", "cream", "butter"})
    if normalize_text(ingredient["category"]) in {"pulse", "grain"}:
        allowed.update({"dry", "dried", "raw", "boiled", "cooked"})
    if normalize_text(ingredient["category"]) == "nut":
        allowed.update({"dry", "dried", "raw", "roasted", "toasted"})

    food_tokens = set(food["name_normalized"].split()) | food["form_tokens"]
    derived_in_food = (food_tokens & DERIVED_FOOD_TERMS) - allowed
    return 1 if derived_in_food else 0


def _default_form_penalty(ingredient: dict[str, Any], food: dict[str, Any]) -> int:
    if normalize_text(ingredient["ingredient_form"]) not in {"", "default"}:
        return 0
    canonical_tokens = set(normalize_text(ingredient["canonical_name"]).split())
    specialized = food["form_tokens"] & DEFAULT_FORM_PENALTY_CUES
    penalty = int(bool(specialized - canonical_tokens))
    if (
        normalize_text(ingredient["category"]) == "grain"
        and food["form_tokens"] & SPECIALIZED_GRAIN_CUES
    ):
        penalty += 1
    return penalty


def _regular_grain_priority(ingredient: dict[str, Any], food: dict[str, Any]) -> int:
    if normalize_text(ingredient["category"]) != "grain":
        return 1
    return 0 if food["form_tokens"] & REGULAR_GRAIN_CUES else 1


def _candidate_status(
    base_method: str,
    form_signal: str,
    ingredient_form: str,
    candidate_forms: set[str],
    recipe_evidence: dict[str, int],
    cnf_form: str,
) -> tuple[str, str]:
    form = normalize_text(ingredient_form)
    state_forms = {
        "raw",
        "dry",
        "dried",
        "dehydrated",
        "boiled",
        "cooked",
        "fried",
        "roasted",
        "steamed",
        "baked",
    }
    candidate_states = set(cnf_form.split(";")) & state_forms
    ambiguous_state = len(candidate_forms & state_forms) > 1
    has_form_cues = bool(set(cnf_form.split(";")) & DISTINCT_FORM_CUES)
    ambiguous_form = len(candidate_forms & DISTINCT_FORM_CUES) > 1

    if base_method in {"TOKEN_MATCH", "FUZZY_CANDIDATE"}:
        return "REVIEW", "Lexical candidate only; human confirmation required."
    if form_signal == "CONFLICT":
        return (
            "REVIEW",
            f"KitchenPilot form '{ingredient_form}' conflicts with CNF form cues.",
        )
    if form not in {"", "default"} and form_signal != "MATCH":
        return (
            "REVIEW",
            f"KitchenPilot form '{ingredient_form}' is not confirmed by the CNF description.",
        )
    if ambiguous_state and recipe_evidence["unspecified"]:
        return (
            "REVIEW",
            "Recipe form is not explicit and CNF has multiple raw/dry/cooked alternatives.",
        )
    if form in {"", "default"} and (
        candidate_states or has_form_cues or ambiguous_form
    ):
        note = "KitchenPilot form is default; it does not imply a CNF food form."
        if ambiguous_state or ambiguous_form:
            note += " CNF records include distinct forms."
        if recipe_evidence["unspecified"]:
            note += " Most linked recipe names do not state cooked/raw form."
        return "REVIEW", note
    if base_method in {"EXACT_NAME", "ALIAS_MATCH", "FORM_MATCH"}:
        return (
            "AUTO_CANDIDATE",
            "Strong name/alias candidate only; not an approved mapping.",
        )
    return "REVIEW", "Human confirmation required."


def generate_candidates(
    ingredients: pd.DataFrame,
    cnf_rows: pd.DataFrame,
    mappings: pd.DataFrame,
    recipe_evidence_frame: pd.DataFrame,
) -> pd.DataFrame:
    foods = _unique_cnf_foods(cnf_rows)
    food_by_id = {food["source_food_id"]: food for food in foods}

    print("\n# CNF MATCHING\n")
    print(f"Canonical ingredients: {len(ingredients)}")
    print(f"CNF foods: {len(foods)}\n")
    print("Building CNF search index...")
    index = _build_cnf_index(foods)
    print("Index complete.\n")
    print("Generating candidates...")

    alias_lookup = _validated_aliases(mappings, ingredients)
    result_rows: list[dict[str, Any]] = []
    total_ing = len(ingredients)

    for idx, ingredient in enumerate(ingredients.to_dict(orient="records"), start=1):
        ingredient_id = ingredient["ingredient_id"]
        canonical_name = ingredient["canonical_name"]
        print(f"[{idx}/{total_ing}] {canonical_name}")

        aliases = alias_lookup.get(ingredient_id, [])
        queries = _query_terms(ingredient, aliases)
        recipe_evidence = _recipe_form_evidence(recipe_evidence_frame, ingredient_id)
        evidence_label = _evidence_label(recipe_evidence)
        canonical_form = ingredient["ingredient_form"]
        prefer_dry = (
            normalize_text(ingredient["category"]) in {"grain", "pulse"}
            and recipe_evidence["unspecified"]
            > recipe_evidence["cooked"] + recipe_evidence["boiled"]
        )

        matches: dict[str, dict[str, Any]] = {}

        # A. EXACT NAME MATCH
        for q in queries:
            norm_q = normalize_text(q["term"])
            if not norm_q:
                continue
            if q["kind"] in {"canonical_name", "display_name"}:
                for food in index["exact"].get(norm_q, []):
                    fid = food["source_food_id"]
                    matches[fid] = {
                        "base_method": "EXACT_NAME",
                        "score": 1.0,
                        "matched_term": q["term"],
                        "term_kind": q["kind"],
                    }
            elif q["kind"] == "form_alias":
                for food in index["exact"].get(norm_q, []):
                    fid = food["source_food_id"]
                    if fid not in matches or matches[fid]["score"] < 0.96:
                        matches[fid] = {
                            "base_method": "FORM_MATCH",
                            "score": 0.96,
                            "matched_term": q["term"],
                            "term_kind": q["kind"],
                        }

        # B. VALIDATED ALIAS MATCH
        for q in queries:
            norm_q = normalize_text(q["term"])
            if not norm_q:
                continue
            if q["kind"].startswith("validated:"):
                for food in index["exact"].get(norm_q, []):
                    fid = food["source_food_id"]
                    if fid not in matches or METHOD_PRIORITY["ALIAS_MATCH"] < METHOD_PRIORITY[matches[fid]["base_method"]]:
                        matches[fid] = {
                            "base_method": "ALIAS_MATCH",
                            "score": 0.97,
                            "matched_term": q["term"],
                            "term_kind": q["kind"],
                        }
            for food in index["alternate"].get(norm_q, []):
                fid = food["source_food_id"]
                if fid not in matches or METHOD_PRIORITY["ALIAS_MATCH"] < METHOD_PRIORITY[matches[fid]["base_method"]]:
                    matches[fid] = {
                        "base_method": "ALIAS_MATCH",
                        "score": 0.96,
                        "matched_term": q["term"],
                        "term_kind": q["kind"],
                    }

        # C. FORM-AWARE TOKEN MATCH
        meaningful_tokens = set()
        for q in queries:
            for t in normalize_text(q["term"]).split():
                if t not in MATCH_STOPWORDS and len(t) > 1:
                    meaningful_tokens.add(t)
        candidate_ids = set()
        for t in meaningful_tokens:
            candidate_ids.update(index["tokens"].get(t, set()))

        for fid in candidate_ids:
            food = food_by_id[fid]
            match = _best_candidate_match(queries, food)
            if match is not None:
                if fid not in matches or (
                    METHOD_PRIORITY[match["base_method"]],
                    -match["score"],
                ) < (
                    METHOD_PRIORITY[matches[fid]["base_method"]],
                    -matches[fid]["score"],
                ):
                    matches[fid] = match

        # D. RESTRICTED FUZZY MATCH
        if len(matches) < FUZZY_FILL_LIMIT:
            fuzzy_candidate_pool = [
                food_by_id[fid] for fid in candidate_ids if fid not in matches
            ]
            if fuzzy_candidate_pool:
                for fid, fuzzy_match in _fuzzy_candidates(
                    queries, fuzzy_candidate_pool, set(matches)
                ):
                    matches[fid] = fuzzy_match

        candidate_form_sets = {
            food_id: set(food_by_id[food_id]["cnf_form"].split(";"))
            for food_id in matches
        }
        all_candidate_forms = (
            set().union(*candidate_form_sets.values()) if candidate_form_sets else set()
        )

        ranked: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        for food_id, match in matches.items():
            food = food_by_id[food_id]
            form_signal = _form_signal(canonical_form, food)
            method_parts = [match["base_method"]]
            if form_signal == "MATCH" and "FORM_MATCH" not in method_parts:
                method_parts.append("FORM_MATCH")
            elif form_signal == "CONFLICT":
                method_parts.append("FORM_CONFLICT")

            score = match["score"]
            if form_signal == "MATCH":
                score += 0.04
            elif form_signal == "CONFLICT":
                score -= 0.12
            score = round(max(0.0, min(1.0, score)), 4)

            status, status_note = _candidate_status(
                match["base_method"],
                form_signal,
                canonical_form,
                all_candidate_forms,
                recipe_evidence,
                food["cnf_form"],
            )
            notes = [status_note]
            if prefer_dry and _is_dry_form(food):
                notes.append(
                    "Ranked ahead as a dry/raw candidate because most recipe entries are unqualified; review required."
                )
            if match["term_kind"].startswith("validated:"):
                notes.append("Alias evidence came from a VALID prior mapping row.")

            primary_priority = 0 if _is_primary_identity(ingredient, food, aliases) else 1
            derived_form_penalty = _derived_form_penalty(ingredient, food)
            dry_priority = 0 if prefer_dry and _is_dry_form(food) else 1
            default_form_penalty = _default_form_penalty(ingredient, food)
            form_prio = _form_compatibility_priority(form_signal)

            sort_key = (
                primary_priority,
                derived_form_penalty,
                dry_priority,
                _regular_grain_priority(ingredient, food),
                default_form_penalty,
                form_prio,
                METHOD_PRIORITY[match["base_method"]],
                -score,
                normalize_text(food["food_name"]),
                int(food_id) if food_id.isdigit() else food_id,
            )
            ranked.append(
                (
                    sort_key,
                    {
                        "ingredient_id": ingredient_id,
                        "canonical_name": ingredient["canonical_name"],
                        "display_name": ingredient["display_name"],
                        "ingredient_form": canonical_form,
                        "category": ingredient["category"],
                        "cnf_food_code": food_id,
                        "cnf_food_name": food["food_name"],
                        "cnf_food_description": food["food_description"],
                        "cnf_alternate_description": food["alternate_names_en"],
                        "cnf_food_form": food["cnf_form"],
                        "match_method": ";".join(method_parts),
                        "match_score": score,
                        "selection_status": status,
                        "review_notes": " ".join(notes),
                        "matched_term": match["matched_term"],
                        "cnf_food_source_code": food["food_source_code"],
                        "source_usda_ndb_code": food["source_usda_ndb_code"],
                        "source_reference": food["source_reference"],
                        "cnf_food_last_updated_date": food[
                            "source_food_last_updated_date"
                        ],
                        "recipe_form_evidence": evidence_label,
                    },
                )
            )

        ranked.sort(key=lambda item: item[0])
        primary_ranked = [item for item in ranked if item[0][0] == 0]
        if primary_ranked:
            ranked = primary_ranked
        ranked = ranked[:MAX_CANDIDATES_PER_INGREDIENT]
        if not ranked:
            result_rows.append(
                {
                    "ingredient_id": ingredient_id,
                    "canonical_name": ingredient["canonical_name"],
                    "display_name": ingredient["display_name"],
                    "ingredient_form": canonical_form,
                    "category": ingredient["category"],
                    "cnf_food_code": "",
                    "cnf_food_name": "",
                    "cnf_food_description": "",
                    "cnf_alternate_description": "",
                    "cnf_food_form": "",
                    "match_method": "NO_MATCH",
                    "match_score": 0.0,
                    "selection_status": "NO_MATCH",
                    "review_notes": "No plausible CNF candidate met the deterministic or fuzzy review thresholds.",
                    "matched_term": "",
                    "cnf_food_source_code": "",
                    "source_usda_ndb_code": "",
                    "source_reference": "",
                    "cnf_food_last_updated_date": "",
                    "recipe_form_evidence": evidence_label,
                    "candidate_rank": 1,
                }
            )
            continue

        for rank, (_, candidate) in enumerate(ranked, start=1):
            result_rows.append({**candidate, "candidate_rank": rank})

    return pd.DataFrame(result_rows, columns=OUTPUT_COLUMNS)


def print_summary(ingredients: pd.DataFrame, candidates: pd.DataFrame) -> None:
    no_match = candidates[candidates["selection_status"] == "NO_MATCH"]
    matched_ids = set(
        candidates.loc[candidates["cnf_food_code"] != "", "ingredient_id"]
    )
    statuses = candidates["selection_status"].value_counts()
    total_ingredients = len(ingredients)

    print("\n" + "=" * 50)
    print("CNF MATCHING COMPLETE")
    print("=" * 50)
    print(f"\nCanonical ingredients processed: {total_ingredients}")
    print(f"Ingredients with candidates: {len(matched_ids)}")
    print(f"Ingredients with no match: {len(no_match)}")
    print(f"Candidate rows: {len(candidates)}")
    print(f"AUTO_CANDIDATE: {int(statuses.get('AUTO_CANDIDATE', 0))}")
    print(f"REVIEW: {int(statuses.get('REVIEW', 0))}")
    print(f"NO_MATCH: {int(statuses.get('NO_MATCH', 0))}")
    print(f"\nOutput:\n{OUTPUT_FILE}")

    examples = [
        "rice",
        "toor dal",
        "moong dal",
        "chickpea flour",
        "turmeric",
        "cumin",
        "onion",
        "tomato",
        "ginger",
        "garlic",
        "ghee",
        "milk",
        "almond",
        "banana",
    ]
    print("\nRepresentative candidates:")
    for name in examples:
        ingredients_for_name = ingredients.loc[
            ingredients["canonical_name"].str.casefold().eq(name),
            ["ingredient_id", "display_name", "ingredient_form"],
        ]
        print(f"\n{name}:")
        if ingredients_for_name.empty:
            print("  Not present in ingredients.csv; no canonical ID to match.")
            continue
        for ingredient in ingredients_for_name.to_dict(orient="records"):
            rows = candidates[
                candidates["ingredient_id"].eq(ingredient["ingredient_id"])
                & candidates["cnf_food_code"].ne("")
            ].head(3)
            print(
                f"  {ingredient['ingredient_id']} {ingredient['display_name']} "
                f"({ingredient['ingredient_form']}):"
            )
            if rows.empty:
                print("    No candidate generated (NO_MATCH).")
                continue
            for row in rows.to_dict(orient="records"):
                print(
                    f"    #{row['candidate_rank']} {row['cnf_food_code']} "
                    f"{row['cnf_food_name']} [{row['cnf_food_form']}] "
                    f"{row['match_method']} {row['match_score']:.3f} "
                    f"{row['selection_status']}"
                )


def main() -> None:
    start_time = time.perf_counter()
    ingredients, cnf_rows, mappings, recipe_evidence = _load_inputs()
    if ingredients["ingredient_id"].eq("").any():
        raise ValueError("ingredients.csv contains a blank ingredient_id")
    if ingredients["ingredient_id"].duplicated().any():
        raise ValueError("ingredients.csv contains duplicate ingredient_id values")

    candidates = generate_candidates(ingredients, cnf_rows, mappings, recipe_evidence)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(OUTPUT_FILE, index=False, encoding="utf-8", na_rep="")
    print_summary(ingredients, candidates)
    elapsed = time.perf_counter() - start_time
    print(f"\nExecution time: {elapsed:.2f}s")


if __name__ == "__main__":
    main()
