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
    """Verify POST /api/v1/recommend/semantic returns valid 200 response with recommendations when enabled."""
    with TestClient(app) as client:
        orig_flag = getattr(app.state.recommender.config, "semantic_retrieval_enabled", False)
        app.state.recommender.config.semantic_retrieval_enabled = True
        try:
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
        finally:
            app.state.recommender.config.semantic_retrieval_enabled = orig_flag


def test_api_recommend_semantic_disabled_returns_503():
    """Verify POST /api/v1/recommend/semantic returns 503 Service Unavailable when feature is disabled."""
    with TestClient(app) as client:
        orig_flag = getattr(app.state.recommender.config, "semantic_retrieval_enabled", False)
        app.state.recommender.config.semantic_retrieval_enabled = False
        try:
            payload = {
                "query": "vegetarian South Indian breakfast with lentils",
                "top_k": 5,
            }
            response = client.post("/api/v1/recommend/semantic", json=payload)
            assert response.status_code == 503
            data = response.json()
            assert "disabled" in data["detail"].lower()
        finally:
            app.state.recommender.config.semantic_retrieval_enabled = orig_flag


def test_api_recommend_semantic_validation_error():
    """Verify empty query string triggers 422 Unprocessable Entity."""
    with TestClient(app) as client:
        response = client.post("/api/v1/recommend/semantic", json={"query": "   ", "top_k": 5})
        assert response.status_code == 422


# ============================================================================
# 11. ONNX Backend & Parity Tests
# ============================================================================

def test_bge_embedder_onnx_backend():
    """Verify BGEEmbedder loads via ONNX runtime, generates 384-d normalized vector deterministically."""
    embedder = BGEEmbedder(backend="onnx")
    assert embedder.backend == "onnx"

    vec = embedder.encode_text("crispy masala dosa with sambar")
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (384,)
    assert vec.dtype == np.float32

    # L2 unit norm
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-4

    # Determinism
    vec2 = embedder.encode_text("crispy masala dosa with sambar")
    np.testing.assert_allclose(vec, vec2, atol=1e-6)

    # Batch encoding
    batch = embedder.encode_batch(["recipe one", "recipe two"], batch_size=2)
    assert batch.shape == (2, 384)
    for row in batch:
        assert abs(float(np.linalg.norm(row)) - 1.0) < 1e-4


def test_onnx_pytorch_parity():
    """Verify mathematical parity between ONNX Runtime and PyTorch embeddings."""
    embedder_onnx = BGEEmbedder(backend="onnx")
    embedder_torch = BGEEmbedder(backend="torch")

    test_queries = [
        "crispy masala dosa with sambar",
        "fish soup Bengali style",
        "paneer butter masala with naan",
        "healthy sprouts salad",
    ]

    for q in test_queries:
        v_onnx = embedder_onnx.encode_text(q)
        v_torch = embedder_torch.encode_text(q)

        # High cosine similarity (>= 0.9999) between float representations
        cos_sim = float(np.dot(v_onnx, v_torch))
        assert cos_sim >= 0.9999, f"Low cosine similarity ({cos_sim}) for query '{q}'"
        assert abs(float(np.linalg.norm(v_onnx)) - 1.0) < 1e-4
        assert abs(float(np.linalg.norm(v_torch)) - 1.0) < 1e-4


def test_bge_embedder_invalid_backend():
    """Verify that configuring an invalid or empty inference backend raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported semantic inference backend"):
        BGEEmbedder(backend="tensorflow")

    with pytest.raises(ValueError, match="Invalid semantic inference backend"):
        BGEEmbedder(backend="")

    with pytest.raises(ValueError, match="Invalid semantic inference backend"):
        BGEEmbedder(backend=None)


def test_bge_embedder_onnx_initialization_failure_does_not_fallback(monkeypatch):
    """Verify ONNX initialization failure raises sanitized RuntimeError and does NOT fall back to PyTorch."""
    embedder = BGEEmbedder(backend="onnx")

    def mock_fail():
        raise RuntimeError("Low-level ONNX engine memory failure")

    monkeypatch.setattr(embedder, "_load_onnx_model", mock_fail)

    with pytest.raises(RuntimeError, match="Failed to initialize ONNX semantic inference engine"):
        embedder.load_model()

    assert embedder._active_backend != "torch", "Silent fallback to PyTorch occurred!"
    assert embedder.is_loaded is False


def test_bge_embedder_explicit_pytorch_backend():
    """Verify that PyTorch is loaded only when explicitly configured."""
    embedder = BGEEmbedder(backend="torch")
    assert embedder.backend == "torch"
    embedder.load_model()
    assert embedder._active_backend == "torch"
    vec = embedder.encode_text("tasty sambar with idli")
    assert vec.shape == (384,)
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-4


def test_bge_embedder_torch_initialization_failure(monkeypatch):
    """Verify that PyTorch initialization failure raises sanitized RuntimeError."""
    embedder = BGEEmbedder(backend="torch")

    def mock_fail():
        raise RuntimeError("PyTorch runtime out-of-memory")

    monkeypatch.setattr(embedder, "_load_torch_model", mock_fail)

    with pytest.raises(RuntimeError, match="Failed to initialize PyTorch semantic inference engine"):
        embedder.load_model()

    assert embedder.is_loaded is False


def test_api_recommend_semantic_initialization_failure_sanitized_503(monkeypatch):
    """Verify that semantic retrieval failure returns 503 without leaking local filesystem paths."""
    with TestClient(app) as client:
        orig_flag = getattr(app.state.recommender.config, "semantic_retrieval_enabled", False)
        app.state.recommender.config.semantic_retrieval_enabled = True

        def mock_load():
            raise FileNotFoundError("C:\\Python\\KitchenPilot-V1\\models\\secret\\weights.npy not found")

        monkeypatch.setattr(app.state.recommender, "_load_semantic_retriever", mock_load)
        orig_retriever = app.state.recommender.semantic_retriever
        app.state.recommender.semantic_retriever = None

        try:
            payload = {"query": "biryani", "top_k": 5}
            response = client.post("/api/v1/recommend/semantic", json=payload)
            assert response.status_code == 503
            detail = response.json().get("detail", "")
            # Ensure no local file paths or drive letters are exposed
            assert "C:\\" not in detail
            assert "secret" not in detail
            assert "weights.npy" not in detail
            assert detail == "Semantic retrieval model artifacts are missing or unreadable."
        finally:
            app.state.recommender.config.semantic_retrieval_enabled = orig_flag
            app.state.recommender.semantic_retriever = orig_retriever


def test_semantic_retriever_initialization_failure_handling():
    """Verify that initialization failure raises FileNotFoundError/RuntimeError safely."""
    rec_cfg = RecommendationConfig(
        semantic_retrieval_enabled=True,
        semantic_embeddings_path=Path("non_existent_path.npy"),
    )
    with pytest.raises(FileNotFoundError):
        KitchenPilotRecommender(config=rec_cfg)


def test_satvik_dietary_compliance_with_onnx_backend():
    """Verify Satvik dietary filtering strictly rejects R00014 (Bengali fish soup) using ONNX backend."""
    cfg = RecommendationConfig(
        semantic_retrieval_enabled=True,
        semantic_inference_backend="onnx",
    )
    rec = KitchenPilotRecommender(config=cfg)

    from src.constraints import ConstraintRequest, DietaryConstraints
    req = ConstraintRequest(dietary=DietaryConstraints(satvik=True))

    results = rec.recommend_semantic(
        query="fish soup Bengali style",
        top_k=5,
        constraint_request=req,
    )

    if not results.empty:
        rids = results["recipe_id"].tolist()
        assert "R00014" not in rids, "R00014 (fish soup) leaked through ONNX Satvik recommendation!"
        for name in results["recipe_name"].tolist():
            assert "fish" not in name.lower(), f"Fish recipe leaked: {name}"


# ============================================================================
# 12. TF-IDF Natural-Language Query Fallback Tests
# ============================================================================

def test_tfidf_fallback_disabled_by_default():
    """Verify fallback defaults to disabled and raises RuntimeError / returns 503."""
    cfg = RecommendationConfig(
        semantic_retrieval_enabled=False,
        semantic_fallback_to_tfidf=False,
    )
    assert cfg.semantic_fallback_to_tfidf is False
    rec = KitchenPilotRecommender(config=cfg)

    with pytest.raises(RuntimeError, match="Semantic retrieval is disabled in configuration"):
        rec.recommend_semantic("paneer butter masala")

    with TestClient(app) as client:
        orig_sem = getattr(app.state.recommender.config, "semantic_retrieval_enabled", False)
        orig_fb = getattr(app.state.recommender.config, "semantic_fallback_to_tfidf", False)
        app.state.recommender.config.semantic_retrieval_enabled = False
        app.state.recommender.config.semantic_fallback_to_tfidf = False
        try:
            res = client.post("/api/v1/recommend/semantic", json={"query": "paneer", "top_k": 5})
            assert res.status_code == 503
            assert "disabled" in res.json()["detail"].lower()
        finally:
            app.state.recommender.config.semantic_retrieval_enabled = orig_sem
            app.state.recommender.config.semantic_fallback_to_tfidf = orig_fb


def test_tfidf_fallback_enabled_natural_language_retrieval():
    """Verify TF-IDF fallback enables natural-language query recommendations without dense neural models."""
    cfg = RecommendationConfig(
        semantic_retrieval_enabled=False,
        semantic_fallback_to_tfidf=True,
    )
    rec = KitchenPilotRecommender(config=cfg)

    results = rec.recommend_semantic("crispy dosa with chutney", top_k=5)
    assert not results.empty
    assert len(results) == 5
    assert "recipe_id" in results.columns
    assert "hybrid_score" in results.columns
    assert "similarity_score" in results.columns

    for _, row in results.iterrows():
        assert 0.0 <= row["hybrid_score"] <= 1.0
        assert 0.0 <= row["similarity_score"] <= 1.0
        assert row["recipe_id"].startswith("R")

    # Verify through API endpoint
    with TestClient(app) as client:
        orig_sem = getattr(app.state.recommender.config, "semantic_retrieval_enabled", False)
        orig_fb = getattr(app.state.recommender.config, "semantic_fallback_to_tfidf", False)
        app.state.recommender.config.semantic_retrieval_enabled = False
        app.state.recommender.config.semantic_fallback_to_tfidf = True
        try:
            res = client.post("/api/v1/recommend/semantic", json={"query": "crispy dosa with chutney", "top_k": 5})
            assert res.status_code == 200
            data = res.json()
            assert data["count"] == 5
            assert data["query"]["mode"] == "tfidf_fallback"
            assert len(data["recommendations"]) == 5
            for item in data["recommendations"]:
                assert item["recipe_id"].startswith("R")
                assert item["similarity_score"] > 0.0
        finally:
            app.state.recommender.config.semantic_retrieval_enabled = orig_sem
            app.state.recommender.config.semantic_fallback_to_tfidf = orig_fb


def test_tfidf_fallback_satvik_dietary_compliance_rejects_fish_soup():
    """Verify Satvik dietary constraints strictly reject R00014 (fish soup) and return valid Satvik recipes under TF-IDF fallback."""
    cfg = RecommendationConfig(
        semantic_retrieval_enabled=False,
        semantic_fallback_to_tfidf=True,
    )
    rec = KitchenPilotRecommender(config=cfg)

    from src.constraints import ComplianceStatus, ConstraintRequest, DietaryConstraints
    req = ConstraintRequest(dietary=DietaryConstraints(satvik=True))

    # 1. Negative query test: Fish soup query must NEVER return R00014
    results = rec.recommend_semantic(
        query="fish soup Bengali style",
        top_k=10,
        constraint_request=req,
    )

    if not results.empty:
        rids = results["recipe_id"].tolist()
        assert "R00014" not in rids, "R00014 (Bengali fish soup) leaked through TF-IDF Satvik fallback!"
        for rid in rids:
            ev = rec.constraint_engine.evaluate_candidate(rid, req)
            assert ev.passed, f"Recipe {rid} failed Satvik constraint: {ev.hard_failures}"
            assert ev.dietary_results.get("satvik") == ComplianceStatus.COMPLIANT
        for name in results["recipe_name"].tolist():
            assert "fish" not in name.lower(), f"Fish recipe leaked: {name}"

    # Also test via API
    with TestClient(app) as client:
        orig_sem = getattr(app.state.recommender.config, "semantic_retrieval_enabled", False)
        orig_fb = getattr(app.state.recommender.config, "semantic_fallback_to_tfidf", False)
        app.state.recommender.config.semantic_retrieval_enabled = False
        app.state.recommender.config.semantic_fallback_to_tfidf = True
        try:
            payload = {
                "query": "fish soup Bengali style",
                "top_k": 10,
                "dietary_constraints": {"satvik": True},
            }
            res = client.post("/api/v1/recommend/semantic", json=payload)
            assert res.status_code == 200
            data = res.json()
            rec_rids = [r["recipe_id"] for r in data["recommendations"]]
            assert "R00014" not in rec_rids
            for r in data["recommendations"]:
                assert "fish" not in r["recipe_name"].lower()
                ev = app.state.recommender.constraint_engine.evaluate_candidate(r["recipe_id"], req)
                assert ev.passed, f"API recipe {r['recipe_id']} failed Satvik constraint"
                assert ev.dietary_results.get("satvik") == ComplianceStatus.COMPLIANT

            # 2. Positive query test: A suitable Satvik query returns eligible Satvik recipes
            satvik_query = "cabbage poriyal coconut"
            satvik_results = rec.recommend_semantic(
                query=satvik_query,
                top_k=5,
                constraint_request=req,
            )
            assert not satvik_results.empty, "Expected positive Satvik recommendations for cabbage poriyal"
            assert len(satvik_results) > 0
            satvik_rids = satvik_results["recipe_id"].tolist()
            assert "R00014" not in satvik_rids
            assert "R00122" in satvik_rids, "Expected R00122 (Muttaikose Poriyal) among Satvik recommendations"

            # Verify every returned recipe satisfies Satvik constraint
            for rid in satvik_rids:
                ev = rec.constraint_engine.evaluate_candidate(rid, req)
                assert ev.passed, f"Recipe {rid} failed Satvik constraint: {ev.hard_failures}"
                assert ev.dietary_results.get("satvik") == ComplianceStatus.COMPLIANT

            # Positive query via API
            api_payload = {
                "query": satvik_query,
                "top_k": 5,
                "dietary_constraints": {"satvik": True},
            }
            api_res = client.post("/api/v1/recommend/semantic", json=api_payload)
            assert api_res.status_code == 200
            api_data = api_res.json()
            assert api_data["count"] > 0
            assert len(api_data["recommendations"]) > 0
            api_rids = [r["recipe_id"] for r in api_data["recommendations"]]
            assert "R00014" not in api_rids
            assert "R00122" in api_rids
            for r in api_data["recommendations"]:
                ev = app.state.recommender.constraint_engine.evaluate_candidate(r["recipe_id"], req)
                assert ev.passed
                assert ev.dietary_results.get("satvik") == ComplianceStatus.COMPLIANT
        finally:
            app.state.recommender.config.semantic_retrieval_enabled = orig_sem
            app.state.recommender.config.semantic_fallback_to_tfidf = orig_fb


def test_tfidf_fallback_enforces_indian_only():
    """Verify only approved Indian cuisine recipes are eligible under TF-IDF fallback."""
    from src.data.cuisine_policy import is_indian_cuisine

    cfg = RecommendationConfig(
        semantic_retrieval_enabled=False,
        semantic_fallback_to_tfidf=True,
    )
    rec = KitchenPilotRecommender(config=cfg)

    results = rec.recommend_semantic("pasta noodles soup", top_k=10)
    for rid in results["recipe_id"]:
        cuisine = rec._recipe_metadata.get(rid, {}).get("cuisine")
        assert is_indian_cuisine(cuisine), f"Non-Indian recipe {rid} with cuisine '{cuisine}' recommended!"


def test_tfidf_fallback_empty_and_unknown_vocabulary_queries():
    """Verify empty query and unknown vocabulary queries are handled safely without exceptions."""
    cfg = RecommendationConfig(
        semantic_retrieval_enabled=False,
        semantic_fallback_to_tfidf=True,
    )
    rec = KitchenPilotRecommender(config=cfg)

    # Empty query string
    res_empty = rec.recommend_semantic("", top_k=5)
    assert res_empty.empty

    res_spaces = rec.recommend_semantic("     ", top_k=5)
    assert res_spaces.empty

    # Unknown vocabulary (out of vocabulary)
    res_oov = rec.recommend_semantic("qwertyuiopasdfghjklzxcvbnm987654321", top_k=5)
    assert res_oov.empty

    # Test via API for unknown vocabulary
    with TestClient(app) as client:
        orig_sem = getattr(app.state.recommender.config, "semantic_retrieval_enabled", False)
        orig_fb = getattr(app.state.recommender.config, "semantic_fallback_to_tfidf", False)
        app.state.recommender.config.semantic_retrieval_enabled = False
        app.state.recommender.config.semantic_fallback_to_tfidf = True
        try:
            res = client.post(
                "/api/v1/recommend/semantic",
                json={"query": "qwertyuiopasdfghjklzxcvbnm987654321", "top_k": 5},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["count"] == 0
            assert data["recommendations"] == []
            assert "No recipes matched" in data["message"]
        finally:
            app.state.recommender.config.semantic_retrieval_enabled = orig_sem
            app.state.recommender.config.semantic_fallback_to_tfidf = orig_fb


def test_tfidf_fallback_missing_artifacts_safely_handled():
    """Verify that if TF-IDF artifacts are missing or unready, clean 503 is returned without leaking paths."""
    from unittest.mock import PropertyMock

    with TestClient(app) as client:
        orig_sem = getattr(app.state.recommender.config, "semantic_retrieval_enabled", False)
        orig_fb = getattr(app.state.recommender.config, "semantic_fallback_to_tfidf", False)
        app.state.recommender.config.semantic_retrieval_enabled = False
        app.state.recommender.config.semantic_fallback_to_tfidf = True
        try:
            retriever = app.state.recommender._get_tfidf_retriever()
            with patch.object(type(retriever), "is_ready", new_callable=PropertyMock) as mock_ready:
                mock_ready.return_value = False
                res = client.post("/api/v1/recommend/semantic", json={"query": "dosa", "top_k": 5})
                assert res.status_code == 503
                detail = res.json().get("detail", "")
                assert "C:\\" not in detail
                assert detail == "Semantic recommendation service is temporarily unavailable."
        finally:
            app.state.recommender.config.semantic_retrieval_enabled = orig_sem
            app.state.recommender.config.semantic_fallback_to_tfidf = orig_fb


def test_tfidf_fallback_does_not_load_dense_neural_packages():
    """Verify in an isolated Python process that running the fallback path does not import torch, transformers, or onnxruntime."""
    import subprocess
    import sys

    probe_script = (
        "import sys\n"
        "from src.recommendation.config import RecommendationConfig\n"
        "from src.recommendation.recommender import KitchenPilotRecommender\n"
        "cfg = RecommendationConfig(semantic_retrieval_enabled=False, semantic_fallback_to_tfidf=True)\n"
        "rec = KitchenPilotRecommender(config=cfg)\n"
        "res = rec.recommend_semantic('south indian dosa', top_k=5)\n"
        "assert not res.empty\n"
        "forbidden = ['torch', 'transformers', 'onnxruntime', 'onnx']\n"
        "loaded = [pkg for pkg in forbidden if pkg in sys.modules]\n"
        "assert not loaded, f'Neural packages loaded: {loaded}'\n"
        "print('ISOLATION_PASSED')\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c", probe_script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"Isolation probe failed: {proc.stderr}"
    assert "ISOLATION_PASSED" in proc.stdout
