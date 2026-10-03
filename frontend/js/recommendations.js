/**
 * KitchenPilot-V1 — Recommendation Builder Controller (recommendations.js)
 * Manages ingredient tagging, preference filters, nutrition targets, and POST /api/v1/recommend/by-ingredients.
 */

let ingredientsList = [];

document.addEventListener("DOMContentLoaded", () => {
    const inputEl = document.getElementById("ingredient-input");
    const btnAdd = document.getElementById("btn-add-ingredient");
    const btnSample = document.getElementById("btn-sample-pantry");
    const btnClear = document.getElementById("btn-clear-ingredients");
    const form = document.getElementById("recommend-form");

    // Enter key or comma to add tag
    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            addIngredientFromInput();
        }
    });

    if (btnAdd) {
        btnAdd.addEventListener("click", addIngredientFromInput);
    }

    if (btnSample) {
        btnSample.addEventListener("click", () => {
            setIngredients(["rice", "onion", "tomato", "cumin", "turmeric"]);
        });
    }

    if (btnClear) {
        btnClear.addEventListener("click", () => {
            setIngredients([]);
        });
    }

    if (form) {
        form.addEventListener("submit", handleFormSubmit);
    }

    // Default sample on initial visit if empty
    setIngredients(["rice", "onion", "tomato", "cumin", "turmeric"]);
});

function addIngredientFromInput() {
    const inputEl = document.getElementById("ingredient-input");
    const text = inputEl.value.trim();
    if (!text) return;

    // Support comma-separated batch input
    const parts = text.split(",").map(p => p.trim().toLowerCase()).filter(p => p.length > 0);
    parts.forEach(part => {
        if (!ingredientsList.includes(part)) {
            ingredientsList.push(part);
        }
    });

    inputEl.value = "";
    renderIngredientTags();
}

function setIngredients(list) {
    ingredientsList = [...list];
    renderIngredientTags();
}

function removeIngredient(index) {
    ingredientsList.splice(index, 1);
    renderIngredientTags();
}

function renderIngredientTags() {
    const container = document.getElementById("ingredient-tags");
    container.innerHTML = "";

    if (ingredientsList.length === 0) {
        container.innerHTML = `<span style="color: var(--text-light); font-size: 0.85rem; padding: 0.25rem;">No ingredients added yet. Type an ingredient above and press Enter.</span>`;
        return;
    }

    ingredientsList.forEach((ing, idx) => {
        const tag = document.createElement("span");
        tag.className = "tag-item";
        tag.innerHTML = `
            <span>${escapeHtml(ing)}</span>
            <button type="button" class="tag-remove" aria-label="Remove ${escapeHtml(ing)}">&times;</button>
        `;
        tag.querySelector(".tag-remove").addEventListener("click", () => removeIngredient(idx));
        container.appendChild(tag);
    });
}

async function handleFormSubmit(e) {
    e.preventDefault();

    const statusContainer = document.getElementById("recommendations-status");
    const grid = document.getElementById("recommendations-grid");
    const resultsHeader = document.getElementById("results-header");
    const resultsMeta = document.getElementById("results-meta");

    grid.innerHTML = "";
    resultsHeader.style.display = "none";
    statusContainer.innerHTML = `
        <div class="state-box">
            <div class="spinner"></div>
            <h3>Computing Hybrid Recommendations...</h3>
            <p>Evaluating TF-IDF similarities, canonical ingredient overlap, and nutritional targets.</p>
        </div>
    `;

    // Construct Payload strictly conforming to Pydantic Schemas
    const topK = parseInt(document.getElementById("select-top-k").value, 10) || 5;

    // User Preferences (only non-null fields)
    const userPrefs = {};
    if (document.getElementById("pref-veg").checked) userPrefs.vegetarian = true;
    if (document.getElementById("pref-vegan").checked) userPrefs.vegan = true;
    if (document.getElementById("pref-jain").checked) userPrefs.jain = true;
    if (document.getElementById("pref-satvik").checked) userPrefs.satvik = true;

    const cuisine = document.getElementById("pref-cuisine").value.trim();
    if (cuisine) userPrefs.cuisine = cuisine;

    const region = document.getElementById("pref-region").value.trim();
    if (region) userPrefs.region = region;

    const mealType = document.getElementById("pref-meal-type").value.trim();
    if (mealType) userPrefs.meal_type = mealType;

    const category = document.getElementById("pref-category").value.trim();
    if (category) userPrefs.category = category;

    // Nutrition Goals (only non-negative values)
    const nutGoals = {};
    const maxCal = parseFloat(document.getElementById("nut-max-cal").value);
    if (!isNaN(maxCal) && maxCal >= 0) nutGoals.max_calories = maxCal;

    const minProt = parseFloat(document.getElementById("nut-min-prot").value);
    if (!isNaN(minProt) && minProt >= 0) nutGoals.min_protein = minProt;

    const maxFat = parseFloat(document.getElementById("nut-max-fat").value);
    if (!isNaN(maxFat) && maxFat >= 0) nutGoals.max_fat = maxFat;

    const maxCarbs = parseFloat(document.getElementById("nut-max-carbs").value);
    if (!isNaN(maxCarbs) && maxCarbs >= 0) nutGoals.max_carbs = maxCarbs;

    const minFiber = parseFloat(document.getElementById("nut-min-fiber").value);
    if (!isNaN(minFiber) && minFiber >= 0) nutGoals.min_fiber = minFiber;

    const payload = {
        ingredients: ingredientsList,
        user_preferences: Object.keys(userPrefs).length > 0 ? userPrefs : null,
        nutrition_goals: Object.keys(nutGoals).length > 0 ? nutGoals : null,
        top_k: topK,
    };

    try {
        const data = await window.KitchenPilotApi.getRecommendationsByIngredients(payload);
        statusContainer.innerHTML = "";

        if (!data.recommendations || data.recommendations.length === 0) {
            statusContainer.innerHTML = `
                <div class="state-box">
                    <h3>No Matching Recommendations</h3>
                    <p>No catalog recipes satisfied your combined dietary filters and ingredient criteria. Try easing dietary restrictions or adding more common ingredients.</p>
                </div>
            `;
            return;
        }

        // Show header
        resultsHeader.style.display = "block";
        resultsMeta.textContent = `Found ${data.count} personalized recipes matching your pantry criteria (Top ${topK} ranked).`;

        // Render Recommendation Cards
        data.recommendations.forEach((item) => {
            const card = document.createElement("div");
            card.className = "recipe-card";

            const matchedTags = item.matched_ingredients && item.matched_ingredients.length > 0
                ? item.matched_ingredients.map(m => `<span style="display: inline-block; font-size: 0.75rem; background: #dcfce7; color: #15803d; border-radius: var(--radius-full); padding: 0.15rem 0.5rem; margin: 0.15rem;">✓ ${escapeHtml(m)}</span>`).join(" ")
                : `<span style="font-size: 0.8rem; color: var(--text-light);">None from available list</span>`;

            const missingTags = item.missing_ingredients && item.missing_ingredients.length > 0
                ? item.missing_ingredients.slice(0, 4).map(m => `<span style="display: inline-block; font-size: 0.75rem; background: #f3f4f6; color: #4b5563; border-radius: var(--radius-full); padding: 0.15rem 0.5rem; margin: 0.15rem;">+ ${escapeHtml(m)}</span>`).join(" ")
                : "";

            card.innerHTML = `
                <div>
                    <div class="card-header">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.4rem;">
                            <span class="score-badge">Rank #${item.rank}</span>
                            <span style="font-size: 0.85rem; font-weight: 700; color: var(--primary);">
                                Hybrid: ${(item.hybrid_score * 100).toFixed(1)}%
                            </span>
                        </div>
                        <h3>${escapeHtml(item.recipe_name)}</h3>
                    </div>

                    <!-- Deterministic Natural Language Explanation -->
                    <div class="card-explanation">
                        <strong>Why Recommended:</strong> ${escapeHtml(item.explanation)}
                    </div>

                    <!-- Breakdown signals -->
                    <div class="card-body" style="font-size: 0.85rem; margin-top: 0.75rem;">
                        <div style="margin-bottom: 0.5rem;">
                            <div style="font-weight: 600; color: var(--secondary); margin-bottom: 0.2rem;">Matched Ingredients:</div>
                            <div>${matchedTags}</div>
                        </div>

                        ${missingTags ? `
                        <div style="margin-bottom: 0.5rem;">
                            <div style="font-weight: 600; color: var(--text-light); margin-bottom: 0.2rem;">Missing Ingredients Needed:</div>
                            <div>${missingTags}</div>
                        </div>` : ""}

                        <div style="margin-top: 0.75rem; padding-top: 0.5rem; border-top: 1px dashed var(--border-color); display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--text-light);">
                            <span>Ing Match: <strong>${Math.round(item.ingredient_match_score * 100)}%</strong></span>
                            <span>Similarity: <strong>${Math.round(item.similarity_score * 100)}%</strong></span>
                            <span>Nutr Score: <strong>${Math.round(item.nutrition_score * 100)}%</strong></span>
                        </div>
                    </div>
                </div>

                <div class="card-footer">
                    <span style="font-size: 0.8rem; color: var(--text-light); font-weight: 600;">ID: ${escapeHtml(item.recipe_id)}</span>
                    <a href="recipe.html?recipe_id=${encodeURIComponent(item.recipe_id)}" class="btn btn-outline btn-sm">View Full Recipe &rarr;</a>
                </div>
            `;
            grid.appendChild(card);
        });

        // Scroll to results
        resultsHeader.scrollIntoView({ behavior: "smooth" });

    } catch (err) {
        statusContainer.innerHTML = `
            <div class="error-banner">
                <div>
                    <strong>Recommendation Error:</strong> ${escapeHtml(err.message)}
                </div>
            </div>
        `;
    }
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
