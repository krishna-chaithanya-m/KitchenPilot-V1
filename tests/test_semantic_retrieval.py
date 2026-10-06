"""Stage D — Dedicated Test Suite for Dense Semantic Retrieval (BGE-small-en-v1.5).

Covers:
- Model initialization, metadata, and dimension verification (384)
- Embedding generation, L2 normalization, and determinism
- Corpus loading, deterministic recipe ID ordering, and absence of duplicates
- Artifact integrity, metadata schema, and shape matching
- Semantic retrieval top-K, score bounds, finite values, and valid recipe IDs
- TF-IDF retrieval adapter compliance with Retriever protocol
- Hybrid candidate pool union, deduplication, and provenance tracking
- Feature flag behavior (SEMANTIC_RETRIEVAL_ENABLED=false preserves V1 baseline)
- Failure handling: missing and corrupted artifact error reporting
- API endpoint /api/v1/recommend/semantic
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.recommendation.config import RecommendationConfig
from src.recommendation.recommender import KitchenPilotRecommender
from src.retrieval.base import RetrievalResult, Retriever
from src.retrieval.corpus import (
    RecipeCorpus,
    build_query_semantic_text,
    build_recipe_semantic_text,
)
from src.retrieval.embeddings import BGEEmbedder, DEFAULT_MODEL_NAME, EXPECTED_EMBEDDING_DIM
from src.retrieval.hybrid import HybridCandidate, HybridCandidateRetriever
from src.retrieval.semantic import SemanticRetriever
from src.retrieval.tfidf import TFIDFRetriever

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEMANTIC_DIR = PROJECT_ROOT / "models" / "retrieval" / "semantic"
EMBEDDINGS_PATH = SEMANTIC_DIR / "recipe_embeddings.npy"
INDEX_PATH = SEMANTIC_DIR / "recipe_index.csv"
METADATA_PATH = SEMANTIC_DIR / "metadata.json"
RECIPES_PATH = PROJECT_ROOT / "data" / "processed" / "recipes.csv"
LINKED_PATH = PROJECT_ROOT / "data" / "processed" / "recipe_ingredients_linked.csv"


# ============================================================================
# 1. Model Loading Tests
# ============================================================================

def test_bge_embedder_initialization():
    """Verify BGEEmbedder defaults and metadata."""
    embedder = BGEEmbedder()
    assert embedder.model_name == DEFAULT_MODEL_NAME
    assert embedder.embedding_dimension == EXPECTED_EMBEDDING_DIM
    assert embedder.normalize_embeddings is True
    assert embedder.is_loaded is False


def test_bge_embedder_load_and_dimension():
    """Verify model loads and encodes with dimension 384."""
    embedder = BGEEmbedder()
    embedder.load_model()
    assert embedder.is_loaded is True
    assert embedder.embedding_dimension == 384

    meta = embedder.get_metadata()
    assert meta["model_name"] == DEFAULT_MODEL_NAME
    assert meta["embedding_dimension"] == 384
    assert meta["normalization"] is True


# ============================================================================
# 2. Embedding Tests
# ============================================================================

def test_embedding_output_dimension_and_normalization():
    """Verify single and batch embeddings are normalized unit vectors of dimension 384."""
    embedder = BGEEmbedder()
    vec = embedder.encode_text("crispy masala dosa with sambar")
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (384,)
    assert vec.dtype == np.float32

    # Verify L2 unit norm: ||v||_2 == 1.0
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-4

    # Batch encoding
    batch = embedder.encode_batch(["recipe one", "recipe two"], batch_size=2)
    assert batch.shape == (2, 384)
    batch_norms = np.linalg.norm(batch, axis=1)
    for bn in batch_norms:
        assert abs(float(bn) - 1.0) < 1e-4


def test_embedding_determinism():
    """Verify repeated encoding of identical text produces bitwise-identical vectors."""
    embedder = BGEEmbedder()
    text = "South Indian vegetarian breakfast with lentils and rice"
    vec1 = embedder.encode_text(text)
    vec2 = embedder.encode_text(text)
    np.testing.assert_array_equal(vec1, vec2)


# ============================================================================
# 3. Corpus Representation Tests
# ============================================================================

def test_build_recipe_semantic_text():
    """Verify deterministic recipe text constructor includes expected fields and excludes IDs."""
    text = build_recipe_semantic_text(
        recipe_name="Masala Dosa",
        cuisine="South Indian",
        region="Karnataka",
        meal_type="Breakfast",
        category="Main Course",
        diet_type="Vegetarian",
        vegetarian=True,
        vegan=False,
        jain=False,
        satvik=False,
        ingredients=["rice", "urad dal", "potato", "ghee"],
    )
    assert "Masala Dosa" in text
    assert "Cuisine: South Indian" in text
    assert "Region: Karnataka" in text
    assert "Meal Type: Breakfast" in text
    assert "Diet: Vegetarian" in text
    assert "Ingredients: rice, urad dal, potato, ghee" in text
    # Verify absence of internal identifiers
    assert "R00" not in text
    assert "source_id" not in text


def test_build_query_semantic_text():
    """Verify query string construction for semantic retrieval."""
    q = build_query_semantic_text(
        query="protein lunch",
        cuisine="Punjabi",
        vegetarian=True,
        available_ingredients=["paneer", "spinach"],
    )
    assert "protein lunch" in q
    assert "Cuisine: Punjabi" in q
    assert "Diet: Vegetarian" in q
    assert "Ingredients: paneer, spinach" in q


def test_corpus_loading_and_ordering():
    """Verify RecipeCorpus matches authoritative 6,871 recipe count and is deterministically ordered."""
    corpus = RecipeCorpus(
        recipes_path=RECIPES_PATH,
        linked_ingredients_path=LINKED_PATH,
    )
    assert len(corpus) == 6871
    assert len(corpus.recipe_ids) == 6871
    assert len(corpus.recipe_texts) == 6871

    # Verify no duplicates
    assert len(set(corpus.recipe_ids)) == 6871

    # Verify deterministic ordering: strictly sorted ascending
    sorted_ids = sorted(corpus.recipe_ids)
    assert corpus.recipe_ids == sorted_ids
    assert corpus.recipe_ids[0] == "R00001"
    assert corpus.recipe_ids[-1] == "R14211"


# ============================================================================
# 4. Artifact Integrity Tests
# ============================================================================

def test_semantic_artifacts_exist_and_match():
    """Verify precomputed embeddings matrix, index, and metadata files exist and are aligned."""
    assert EMBEDDINGS_PATH.is_file(), f"Missing {EMBEDDINGS_PATH}"
    assert INDEX_PATH.is_file(), f"Missing {INDEX_PATH}"
    assert METADATA_PATH.is_file(), f"Missing {METADATA_PATH}"

    # Load matrix
    mat = np.load(EMBEDDINGS_PATH)
    assert mat.shape == (6871, 384)
    assert mat.dtype == np.float32

    # Load index
    idx_df = pd.read_csv(INDEX_PATH)
    assert len(idx_df) == 6871
    assert "recipe_id" in idx_df.columns
    assert "row_index" in idx_df.columns

    # Load metadata
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["model_name"] == DEFAULT_MODEL_NAME
    assert meta["embedding_dimension"] == 384
    assert meta["recipe_count"] == 6871
    assert meta["normalization"] == "l2"
    assert "embeddings_sha256" in meta


# ============================================================================
# 5. Semantic Retrieval Tests
# ============================================================================

def test_semantic_retriever_load_and_retrieve():
    """Verify SemanticRetriever loads artifacts and retrieves top-k candidates with valid scores."""
    retriever = SemanticRetriever(
        embeddings_path=EMBEDDINGS_PATH,
        index_path=INDEX_PATH,
        metadata_path=METADATA_PATH,
    )
    retriever.load_artifacts()
    assert retriever.is_ready is True

    # Retrieve top 5
    results = retriever.retrieve("healthy lentils and spinach dal", top_k=5)
    assert len(results) == 5
    for rank, res in enumerate(results, 1):
        assert isinstance(res, RetrievalResult)
        assert res.rank == rank
        assert res.recipe_id.startswith("R")
        assert res.retrieval_method == "semantic"
        assert 0.0 <= res.score <= 1.0
        assert np.isfinite(res.score)

    # Search API method (Section 13)
    dict_results = retriever.search("spicy paneer tikka", top_k=3)
    assert len(dict_results) == 3
    for idx, d in enumerate(dict_results, 1):
        assert d["rank"] == idx
        assert "recipe_id" in d
        assert "score" in d
        assert "embedding" not in d  # Vectors must not be exposed


def test_semantic_retrieval_determinism():
    """Verify querying SemanticRetriever twice returns identical results and scores."""
    retriever = SemanticRetriever(
        embeddings_path=EMBEDDINGS_PATH,
        index_path=INDEX_PATH,
        metadata_path=METADATA_PATH,
    )
    retriever.load_artifacts()

    query = "kashmiri dum aloo with fennel"
    res1 = retriever.retrieve(query, top_k=10)
    res2 = retriever.retrieve(query, top_k=10)

    assert [r.recipe_id for r in res1] == [r.recipe_id for r in res2]
    assert [r.score for r in res1] == [r.score for r in res2]


# ============================================================================
# 6. TF-IDF Adapter Tests
# ============================================================================

def test_tfidf_retriever_adapter():
    """Verify TFIDFRetriever implements the common Retriever protocol."""
    from src.recommendation.tfidf_model import TFIDFModel

    tfidf_model = TFIDFModel()
    tfidf_model.load_artifacts()
    retriever = TFIDFRetriever(tfidf_model)

    assert isinstance(retriever, Retriever)
    assert retriever.is_ready is True

    results = retriever.retrieve("tomato rice", top_k=5)
    assert len(results) == 5
    for res in results:
        assert res.retrieval_method == "tfidf"
        assert 0.0 <= res.score <= 1.0
        assert res.recipe_id.startswith("R")


# ============================================================================
# 7. Hybrid Candidate Retrieval Tests
# ============================================================================

def test_hybrid_candidate_retrieval_and_provenance():
    """Verify candidate union, deduplication, and provenance ('tfidf', 'semantic', 'both')."""
    from src.recommendation.tfidf_model import TFIDFModel

    tfidf_model = TFIDFModel()
    tfidf_model.load_artifacts()
    tfidf_retriever = TFIDFRetriever(tfidf_model)

    semantic_retriever = SemanticRetriever(
        embeddings_path=EMBEDDINGS_PATH,
        index_path=INDEX_PATH,
        metadata_path=METADATA_PATH,
    )
    semantic_retriever.load_artifacts()

    hybrid = HybridCandidateRetriever(
        tfidf_retriever=tfidf_retriever,
        semantic_retriever=semantic_retriever,
        default_tfidf_top_k=20,
        default_semantic_top_k=20,
    )

    candidates = hybrid.retrieve_candidates("south indian dosa with chutney", tfidf_top_k=20, semantic_top_k=20)
    assert len(candidates) > 0

    # Ensure no duplicates
    rids = [c.recipe_id for c in candidates]
    assert len(rids) == len(set(rids))

    # Check provenances
    provenances = {c.provenance for c in candidates}
    assert provenances.issubset({"tfidf", "semantic", "both"})
    assert len(provenances) > 1  # Should contain at least two provenance types


# ============================================================================
# 8. Feature Flag & Backward Compatibility Tests
# ============================================================================

def test_feature_flag_disabled_preserves_v1_baseline():
    """Verify SEMANTIC_RETRIEVAL_ENABLED=false does not load semantic retriever and preserves exact V1 behavior."""
    cfg = RecommendationConfig()
    assert cfg.semantic_retrieval_enabled is False

    recommender = KitchenPilotRecommender(config=cfg)
    assert recommender.semantic_retriever is None

    # Run recommendation
    res = recommender.recommend(available_ingredients=["paneer", "butter", "tomato"], top_k=5, save_results=False)
    assert not res.empty
    assert len(res) == 5
    assert "hybrid_score" in res.columns


# ============================================================================
# 9. Failure Handling Tests
# ============================================================================

def test_failure_handling_missing_artifacts():
    """Verify missing artifacts raise clear FileNotFoundError without silent corruption."""
    retriever = SemanticRetriever(
        embeddings_path=Path("non_existent_embeddings.npy"),
        index_path=Path("non_existent_index.csv"),
    )
    with pytest.raises(FileNotFoundError) as exc_info:
        retriever.load_artifacts()
    assert "missing" in str(exc_info.value).lower()


def test_failure_handling_corrupted_dimension(tmp_path: Path):
    """Verify invalid embedding dimension raises ValueError."""
    fake_matrix = np.ones((10, 128), dtype=np.float32)  # Wrong dimension (128 instead of 384)
    fake_emb_path = tmp_path / "bad_emb.npy"
    fake_idx_path = tmp_path / "bad_idx.csv"
    np.save(fake_emb_path, fake_matrix)

    pd.DataFrame({"recipe_id": [f"R{i:05d}" for i in range(10)], "row_index": list(range(10))}).to_csv(
        fake_idx_path, index=False
    )

    retriever = SemanticRetriever(
        embeddings_path=fake_emb_path,
        index_path=fake_idx_path,
    )
    with pytest.raises(ValueError) as exc_info:
        retriever.load_artifacts()
    assert "dimension mismatch" in str(exc_info.value).lower()


# ============================================================================
# 10. API Route Tests
# ============================================================================

def test_api_recommend_semantic_success():
    """Verify POST /api/v1/recommend/semantic returns valid 200 response with recommendations."""
    with TestClient(app) as client:
        payload = {
            "query": "vegetarian South Indian breakfast with lentils",
            "top_k": 5,
            "user_preferences": {"vegetarian": True},
        }
        response = client.post("/api/v1/recommend/semantic", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5
        assert len(data["recommendations"]) == 5
        rec0 = data["recommendations"][0]
        assert "recipe_id" in rec0
        assert "recipe_name" in rec0
        assert "hybrid_score" in rec0
        assert "similarity_score" in rec0
        assert "explanation" in rec0
        assert "embedding" not in rec0


def test_api_recommend_semantic_validation_error():
    """Verify empty query string triggers 422 Unprocessable Entity."""
    with TestClient(app) as client:
        response = client.post("/api/v1/recommend/semantic", json={"query": "   ", "top_k": 5})
        assert response.status_code == 422
