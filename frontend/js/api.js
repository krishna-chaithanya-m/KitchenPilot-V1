/**
 * KitchenPilot-V1 — Centralized API Client
 *
 * All frontend requests to the FastAPI backend route through these helpers.
 * Handles JSON serialization, query parameter encoding, and user-friendly error formatting.
 */

const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

/**
 * Resolves the effective API base URL.
 * - Defaults to development URL: http://127.0.0.1:8000/api/v1
 * - Supports runtime override via window.KITCHENPILOT_API_BASE_URL (e.g. "/api/v1" for reverse proxies)
 *
 * @returns {string}
 */
function getApiBaseUrl() {
    if (typeof window !== "undefined" && window.KITCHENPILOT_API_BASE_URL) {
        return window.KITCHENPILOT_API_BASE_URL;
    }
    return API_BASE_URL;
}

/**
 * Custom error class for KitchenPilot API exceptions.
 */
class ApiError extends Error {
    constructor(message, status = 0, detail = null) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.detail = detail;
    }
}

/**
 * Generic fetch wrapper with robust error translation.
 *
 * @param {string} endpoint - Relative path (e.g., "/health", "/recipes")
 * @param {object} options - Fetch options (method, headers, body)
 * @returns {Promise<any>} Parsed JSON response
 */
async function request(endpoint, options = {}) {
    const url = `${getApiBaseUrl()}${endpoint}`;
    const defaultHeaders = {
        "Accept": "application/json",
    };

    if (options.body && typeof options.body === "string") {
        defaultHeaders["Content-Type"] = "application/json";
    }

    const config = {
        ...options,
        headers: {
            ...defaultHeaders,
            ...(options.headers || {}),
        },
    };

    try {
        const response = await fetch(url, config);

        let data = null;
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
            try {
                data = await response.json();
            } catch (jsonErr) {
                data = null;
            }
        }

        if (!response.ok) {
            let message = `API request failed with status ${response.status}`;
            let detail = null;

            if (data && data.detail) {
                detail = data.detail;
                if (typeof data.detail === "string") {
                    message = data.detail;
                } else if (Array.isArray(data.detail)) {
                    // Pydantic validation errors
                    message = data.detail.map(e => `${e.loc ? e.loc.join('.') : 'field'}: ${e.msg}`).join("; ");
                }
            } else if (response.status === 404) {
                message = "The requested resource was not found.";
            } else if (response.status === 503) {
                message = "The recommendation engine or dataset is currently unavailable.";
            } else if (response.status >= 500) {
                message = "An unexpected server error occurred. Please try again later.";
            }

            throw new ApiError(message, response.status, detail);
        }

        return data;
    } catch (err) {
        if (err instanceof ApiError) {
            throw err;
        }
        // Network connection error / CORS / Server not running
        throw new ApiError(
            "Cannot connect to the KitchenPilot backend. Please ensure the FastAPI server is running on http://127.0.0.1:8000.",
            0,
            err.message
        );
    }
}

/**
 * Health check endpoint.
 * GET /api/v1/health
 */
async function checkHealth() {
    return request("/health");
}

/**
 * System readiness probe.
 * GET /api/v1/health/ready
 */
async function checkReadiness() {
    return request("/health/ready");
}

/**
 * Paginated recipe catalog listing.
 * GET /api/v1/recipes
 *
 * @param {object} params - { page, page_size, cuisine, region, meal_type, category, vegetarian, vegan, jain, satvik }
 */
async function listRecipes(params = {}) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined && value !== "") {
            query.append(key, value);
        }
    }
    const qs = query.toString();
    return request(`/recipes${qs ? `?${qs}` : ""}`);
}

/**
 * Fetch recipe details by ID.
 * GET /api/v1/recipes/{recipe_id}
 */
async function getRecipe(recipeId) {
    if (!recipeId) {
        throw new ApiError("Recipe ID is required.", 400);
    }
    return request(`/recipes/${encodeURIComponent(recipeId)}`);
}

/**
 * Fetch standalone frozen nutrition for a recipe.
 * GET /api/v1/recipes/{recipe_id}/nutrition
 */
async function getRecipeNutrition(recipeId) {
    if (!recipeId) {
        throw new ApiError("Recipe ID is required.", 400);
    }
    return request(`/recipes/${encodeURIComponent(recipeId)}/nutrition`);
}

/**
 * Find similar recipes using TF-IDF.
 * GET /api/v1/recipes/{recipe_id}/similar?top_k={topK}
 */
async function getSimilarRecipes(recipeId, topK = 10) {
    if (!recipeId) {
        throw new ApiError("Recipe ID is required.", 400);
    }
    return request(`/recipes/${encodeURIComponent(recipeId)}/similar?top_k=${encodeURIComponent(topK)}`);
}

/**
 * General recommendation endpoint.
 * POST /api/v1/recommend
 *
 * @param {object} payload - { query_recipe_id, available_ingredients, user_preferences, nutrition_goals, top_k }
 */
async function getRecommendations(payload) {
    return request("/recommend", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

/**
 * Ingredient-focused recommendation endpoint.
 * POST /api/v1/recommend/by-ingredients
 *
 * @param {object} payload - { ingredients, user_preferences, nutrition_goals, top_k }
 */
async function getRecommendationsByIngredients(payload) {
    return request("/recommend/by-ingredients", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

// Export functions to window for vanilla JS multi-page usage
window.KitchenPilotApi = {
    API_BASE_URL,
    getApiBaseUrl,
    ApiError,
    checkHealth,
    checkReadiness,
    listRecipes,
    getRecipe,
    getRecipeNutrition,
    getSimilarRecipes,
    getRecommendations,
    getRecommendationsByIngredients,
};
