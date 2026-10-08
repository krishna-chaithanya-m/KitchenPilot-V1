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
    if (typeof localStorage !== "undefined") {
        const stored = localStorage.getItem("kitchenpilot_api_base_url");
        if (stored && stored.trim()) {
            return stored.trim().replace(/\/+$/, "");
        }
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

    const token = typeof localStorage !== "undefined" ? localStorage.getItem("kitchenpilot_token") : null;
    if (token) {
        defaultHeaders["Authorization"] = `Bearer ${token}`;
    }

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
            `Cannot connect to the KitchenPilot backend (${getApiBaseUrl()}). Please ensure the API server is running and reachable.`,
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

/**
 * Authentication and User Helpers (Stage G)
 */
function getAuthToken() {
    return typeof localStorage !== "undefined" ? localStorage.getItem("kitchenpilot_token") : null;
}

function setAuthToken(token) {
    if (typeof localStorage !== "undefined") {
        localStorage.setItem("kitchenpilot_token", token);
    }
}

function clearAuthToken() {
    if (typeof localStorage !== "undefined") {
        localStorage.removeItem("kitchenpilot_token");
        localStorage.removeItem("kitchenpilot_user");
    }
}

async function register(email, password, displayName, inviteCode) {
    const payload = { email, password, display_name: displayName || null };
    if (inviteCode) {
        payload.invite_code = inviteCode;
    }
    const data = await request("/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
    });
    if (data && data.access_token) {
        setAuthToken(data.access_token);
        if (typeof localStorage !== "undefined") {
            localStorage.setItem("kitchenpilot_user", JSON.stringify(data.user));
        }
    }
    return data;
}

async function login(email, password) {
    const data = await request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
    });
    if (data && data.access_token) {
        setAuthToken(data.access_token);
        if (typeof localStorage !== "undefined") {
            localStorage.setItem("kitchenpilot_user", JSON.stringify(data.user));
        }
    }
    return data;
}

function logout() {
    clearAuthToken();
}

async function getUserProfile() {
    return request("/user/profile");
}

async function updateUserPreferences(preferences) {
    return request("/user/preferences", {
        method: "PUT",
        body: JSON.stringify(preferences),
    });
}

async function updatePreferences(preferences) {
    return updateUserPreferences(preferences);
}

async function updateUserNutritionTargets(targets) {
    return request("/user/nutrition-targets", {
        method: "PUT",
        body: JSON.stringify(targets),
    });
}

async function updateNutritionTargets(targets) {
    return updateUserNutritionTargets(targets);
}

async function getUserPantry() {
    return request("/user/pantry");
}

async function addPantryItem(item) {
    return request("/user/pantry", {
        method: "POST",
        body: JSON.stringify(item),
    });
}

async function deletePantryItem(itemId) {
    return request(`/user/pantry/${itemId}`, {
        method: "DELETE",
    });
}

async function syncUserPantry(ingredientNames) {
    const existingPantry = await getUserPantry();
    const existingItems = Array.isArray(existingPantry) ? existingPantry : (existingPantry && existingPantry.items ? existingPantry.items : []);
    const targetSet = new Set((ingredientNames || []).map(i => (typeof i === "string" ? i : i.ingredient_name || "").trim().toLowerCase()).filter(Boolean));

    // 1. Delete items no longer in target set
    for (const item of existingItems) {
        const name = (item.ingredient_name || "").trim().toLowerCase();
        if (!targetSet.has(name)) {
            await deletePantryItem(item.id);
        }
    }

    // 2. Identify remaining items in pantry
    const remainingNames = new Set(
        existingItems
            .filter(it => targetSet.has((it.ingredient_name || "").trim().toLowerCase()))
            .map(it => (it.ingredient_name || "").trim().toLowerCase())
    );

    // 3. Add only items that are not yet in the pantry
    const results = [];
    for (const name of (ingredientNames || [])) {
        const clean = (typeof name === "string" ? name : name.ingredient_name || "").trim();
        if (clean && !remainingNames.has(clean.toLowerCase())) {
            const added = await addPantryItem({
                ingredient_name: clean,
                status: "IN_STOCK",
            });
            results.push(added);
            remainingNames.add(clean.toLowerCase());
        }
    }
    return results;
}

async function submitFeedback(recipeId, feedbackType, rating = null, notes = null, sessionId = null) {
    const payload = {
        recipe_id: recipeId,
        feedback_type: feedbackType,
        rating,
        notes,
    };
    if (sessionId) {
        payload.session_id = sessionId;
    }
    return request("/user/feedback", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

async function getUserFeedback(feedbackType = null) {
    const query = feedbackType ? `?feedback_type=${feedbackType}` : "";
    return request(`/user/feedback${query}`);
}

async function getUserHistory(limit = 50, offset = 0) {
    return request(`/user/history?limit=${limit}&offset=${offset}`);
}

async function purgeUserData(deleteAccount = false) {
    const res = await request(`/user/data?delete_account=${deleteAccount}`, {
        method: "DELETE",
    });
    if (deleteAccount) {
        clearAuthToken();
    }
    return res;
}

async function getPilotStatus() {
    return request("/auth/pilot-status");
}

async function getUserPilotStatus() {
    return request("/user/pilot-status");
}

async function deactivateAccount() {
    const res = await request("/user/deactivate", { method: "POST" });
    clearAuthToken();
    return res;
}

async function submitQualitativeFeedback(issueType, comments = null, recipeId = null, sessionId = null) {
    const payload = {
        issue_type: issueType,
        comments,
    };
    if (recipeId) payload.recipe_id = recipeId;
    if (sessionId) payload.session_id = sessionId;
    return request("/user/qualitative-feedback", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

async function getUserQualitativeFeedback(recipeId = null, issueType = null) {
    const params = new URLSearchParams();
    if (recipeId) params.append("recipe_id", recipeId);
    if (issueType) params.append("issue_type", issueType);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return request(`/user/qualitative-feedback${qs}`);
}

// Export functions to window for vanilla JS multi-page usage
window.KitchenPilotApi = {
    API_BASE_URL,
    getApiBaseUrl,
    setApiBaseUrl: (url) => {
        if (typeof window !== "undefined" && typeof window.setKitchenPilotEnvironment === "function") {
            return window.setKitchenPilotEnvironment(url);
        }
        if (typeof localStorage !== "undefined") {
            localStorage.setItem("kitchenpilot_api_base_url", url);
        }
        if (typeof window !== "undefined") {
            window.KITCHENPILOT_API_BASE_URL = url;
        }
        return url;
    },
    ApiError,
    checkHealth,
    checkReadiness,
    listRecipes,
    getRecipe,
    getRecipeNutrition,
    getSimilarRecipes,
    getRecommendations,
    getRecommendationsByIngredients,
    getAuthToken,
    setAuthToken,
    clearAuthToken,
    isAuthenticated: () => !!(typeof localStorage !== "undefined" && localStorage.getItem("kitchenpilot_token")),
    register,
    login,
    logout,
    getUserProfile,
    updateUserPreferences,
    updatePreferences: updateUserPreferences,
    updateUserNutritionTargets,
    updateNutritionTargets: updateUserNutritionTargets,
    getUserPantry,
    getPantry: getUserPantry,
    addPantryItem,
    deletePantryItem,
    syncUserPantry,
    syncPantry: syncUserPantry,
    submitFeedback,
    getUserFeedback,
    submitQualitativeFeedback,
    getUserQualitativeFeedback,
    getUserHistory,
    purgeUserData,
    getPilotStatus,
    getUserPilotStatus,
    deactivateAccount,
};
