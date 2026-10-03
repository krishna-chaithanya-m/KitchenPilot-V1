/**
 * KitchenPilot-V1 — Recipe Detail Controller (recipe.js)
 * Manages individual recipe retrieval, nutrition breakdown, and similar recipe queries.
 */

let currentRecipeId = null;

document.addEventListener("DOMContentLoaded", () => {
    const params = new URLSearchParams(window.location.search);
    currentRecipeId = params.get("recipe_id");

    const btnSimilar = document.getElementById("btn-similar-recipes");
    const btnNutrition = document.getElementById("btn-refresh-nutrition");

    if (btnSimilar) {
        btnSimilar.addEventListener("click", loadSimilarRecipes);
    }

    if (btnNutrition) {
        btnNutrition.addEventListener("click", refreshNutrition);
    }

    if (!currentRecipeId) {
        showError("No recipe ID specified. Please select a recipe from the catalog.");
        return;
    }

    loadRecipeDetail(currentRecipeId);
});

async function loadRecipeDetail(recipeId) {
    const statusContainer = document.getElementById("recipe-status");
    const content = document.getElementById("recipe-content");

    statusContainer.innerHTML = `
        <div class="state-box">
            <div class="spinner"></div>
            <h3>Loading Recipe Details...</h3>
            <p>Retrieving recipe metadata and verified nutrition.</p>
        </div>
    `;
    content.style.display = "none";

    try {
        const recipe = await window.KitchenPilotApi.getRecipe(recipeId);
        statusContainer.innerHTML = "";
        content.style.display = "block";

        // Title & Local Name
        document.getElementById("recipe-title").textContent = recipe.recipe_name || "Untitled Recipe";
        const localEl = document.getElementById("recipe-local-name");
        if (recipe.name_local && recipe.name_local !== recipe.recipe_name) {
            localEl.textContent = `Local / Regional Name: ${recipe.name_local}`;
            localEl.style.display = "block";
        } else {
            localEl.style.display = "none";
        }

        // Badges
        const badgesContainer = document.getElementById("recipe-badges");
        badgesContainer.innerHTML = "";

        if (recipe.vegetarian) {
            badgesContainer.innerHTML += `<span class="badge badge-veg">Vegetarian</span>`;
        } else {
            badgesContainer.innerHTML += `<span class="badge badge-nonveg">Non-Veg</span>`;
        }

        if (recipe.vegan) {
            badgesContainer.innerHTML += `<span class="badge badge-veg">Vegan</span>`;
        }
        if (recipe.jain) {
            badgesContainer.innerHTML += `<span class="badge badge-veg">Jain</span>`;
        }
        if (recipe.satvik) {
            badgesContainer.innerHTML += `<span class="badge badge-veg">Satvik</span>`;
        }
        if (recipe.cuisine) {
            badgesContainer.innerHTML += `<span class="badge badge-cuisine">${escapeHtml(recipe.cuisine)}</span>`;
        }
        if (recipe.region) {
            badgesContainer.innerHTML += `<span class="badge badge-cuisine">${escapeHtml(recipe.region)}</span>`;
        }
        if (recipe.diet_type) {
            badgesContainer.innerHTML += `<span class="badge badge-diet">${escapeHtml(recipe.diet_type)}</span>`;
        }

        // Stats Bar
        document.getElementById("stat-prep").textContent = recipe.prep_time_min ? `${recipe.prep_time_min}m` : "-";
        document.getElementById("stat-cook").textContent = recipe.cook_time_min ? `${recipe.cook_time_min}m` : "-";
        document.getElementById("stat-total").textContent = recipe.total_time_min ? `${recipe.total_time_min}m` : "-";
        document.getElementById("stat-servings").textContent = recipe.servings ? `${recipe.servings}` : "-";

        const calPerServing = recipe.nutrition?.calories ? `${Math.round(recipe.nutrition.calories)} kcal` : "N/A";
        document.getElementById("stat-calories").textContent = calPerServing;

        // Ingredients List
        const ingList = document.getElementById("ingredients-list");
        ingList.innerHTML = "";
        if (Array.isArray(recipe.ingredients) && recipe.ingredients.length > 0) {
            recipe.ingredients.forEach((ing) => {
                const li = document.createElement("li");
                li.textContent = ing;
                ingList.appendChild(li);
            });
        } else {
            ingList.innerHTML = `<li>No individual ingredients listed.</li>`;
        }

        // Instructions
        const instrEl = document.getElementById("instructions-container");
        instrEl.textContent = recipe.instructions || "Preparation instructions not provided.";

        // Nutrition Profile
        renderNutrition(recipe.nutrition);

    } catch (err) {
        showError(err.message || "Failed to load recipe details.");
    }
}

function renderNutrition(nut) {
    if (!nut) {
        document.getElementById("nutrition-confidence-badge").textContent = "Status: Unavailable";
        return;
    }

    const badge = document.getElementById("nutrition-confidence-badge");
    const quality = nut.nutrition_quality || "Verified";
    const confidence = nut.nutrition_confidence !== undefined ? `(${Math.round(nut.nutrition_confidence * 100)}% confidence)` : "";
    badge.textContent = `Quality: ${quality} ${confidence}`;

    document.getElementById("nut-cal").textContent = nut.calories !== null && nut.calories !== undefined ? `${Math.round(nut.calories)} kcal` : "-";
    document.getElementById("nut-protein").textContent = nut.protein !== null && nut.protein !== undefined ? `${nut.protein} g` : "-";
    document.getElementById("nut-fat").textContent = nut.fat !== null && nut.fat !== undefined ? `${nut.fat} g` : "-";
    document.getElementById("nut-carbs").textContent = nut.carbs !== null && nut.carbs !== undefined ? `${nut.carbs} g` : "-";
    document.getElementById("nut-fiber").textContent = nut.fiber !== null && nut.fiber !== undefined ? `${nut.fiber} g` : "-";
    document.getElementById("nut-sugar").textContent = nut.sugar !== null && nut.sugar !== undefined ? `${nut.sugar} g` : "-";
    document.getElementById("nut-sodium").textContent = nut.sodium !== null && nut.sodium !== undefined ? `${Math.round(nut.sodium)} mg` : "-";
}

async function refreshNutrition() {
    if (!currentRecipeId) return;
    try {
        const nut = await window.KitchenPilotApi.getRecipeNutrition(currentRecipeId);
        renderNutrition(nut);
        alert(`Nutrition verified: ${Math.round(nut.calories || 0)} kcal/serving (${nut.nutrition_quality || "VALIDATED"}).`);
    } catch (err) {
        alert(`Could not verify nutrition: ${err.message}`);
    }
}

async function loadSimilarRecipes() {
    if (!currentRecipeId) return;

    const section = document.getElementById("similar-section");
    const statusContainer = document.getElementById("similar-status");
    const grid = document.getElementById("similar-grid");

    section.style.display = "block";
    grid.innerHTML = "";
    statusContainer.innerHTML = `
        <div style="text-align: center; padding: 1.5rem;">
            <div class="spinner"></div>
            <p>Computing TF-IDF cosine similarities...</p>
        </div>
    `;

    // Scroll to section
    section.scrollIntoView({ behavior: "smooth" });

    try {
        const data = await window.KitchenPilotApi.getSimilarRecipes(currentRecipeId, 6);
        statusContainer.innerHTML = "";

        if (!data.recommendations || data.recommendations.length === 0) {
            statusContainer.innerHTML = `<p style="color: var(--text-light);">No similar recipes found.</p>`;
            return;
        }

        data.recommendations.forEach((item) => {
            const card = document.createElement("div");
            card.className = "recipe-card";

            card.innerHTML = `
                <div>
                    <div class="card-header">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.35rem;">
                            <span class="score-badge">Rank #${item.rank}</span>
                            <span style="font-size: 0.8rem; font-weight: 700; color: var(--accent-emerald);">Match: ${(item.hybrid_score * 100).toFixed(1)}%</span>
                        </div>
                        <h3>${escapeHtml(item.recipe_name)}</h3>
                    </div>

                    <div class="card-explanation">
                        <strong>Why Recommended:</strong> ${escapeHtml(item.explanation)}
                    </div>
                </div>

                <div class="card-footer">
                    <span style="font-size: 0.8rem; color: var(--text-light); font-weight: 600;">ID: ${escapeHtml(item.recipe_id)}</span>
                    <a href="recipe.html?recipe_id=${encodeURIComponent(item.recipe_id)}" class="btn btn-outline btn-sm">View Recipe &rarr;</a>
                </div>
            `;
            grid.appendChild(card);
        });

    } catch (err) {
        statusContainer.innerHTML = `
            <div class="error-banner">
                <div><strong>Failed to load similar recipes:</strong> ${escapeHtml(err.message)}</div>
            </div>
        `;
    }
}

function showError(msg) {
    const statusContainer = document.getElementById("recipe-status");
    const content = document.getElementById("recipe-content");
    content.style.display = "none";
    statusContainer.innerHTML = `
        <div class="error-banner">
            <div>
                <strong>Error:</strong> ${escapeHtml(msg)}
                <br><br>
                <a href="recipes.html" class="btn btn-secondary btn-sm">Return to Catalog</a>
            </div>
        </div>
    `;
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
