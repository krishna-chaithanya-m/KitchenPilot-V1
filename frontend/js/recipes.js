/**
 * KitchenPilot-V1 — Recipe Catalog Controller (recipes.js)
 * Manages filtering, pagination, and card rendering for GET /api/v1/recipes.
 */

let currentPage = 1;
let currentFilters = {};

document.addEventListener("DOMContentLoaded", () => {
    const filterForm = document.getElementById("recipes-filter-form");
    const btnReset = document.getElementById("btn-reset-filters");
    const btnPrev = document.getElementById("btn-prev-page");
    const btnNext = document.getElementById("btn-next-page");

    if (filterForm) {
        filterForm.addEventListener("submit", (e) => {
            e.preventDefault();
            currentPage = 1;
            applyFilters();
        });
    }

    if (btnReset) {
        btnReset.addEventListener("click", () => {
            filterForm.reset();
            currentPage = 1;
            applyFilters();
        });
    }

    if (btnPrev) {
        btnPrev.addEventListener("click", () => {
            if (currentPage > 1) {
                currentPage--;
                loadRecipes();
            }
        });
    }

    if (btnNext) {
        btnNext.addEventListener("click", () => {
            currentPage++;
            loadRecipes();
        });
    }

    // Initial load
    applyFilters();
});

function applyFilters() {
    const cuisine = document.getElementById("filter-cuisine")?.value.trim() || null;
    const mealType = document.getElementById("filter-meal-type")?.value.trim() || null;
    const category = document.getElementById("filter-category")?.value.trim() || null;
    const pageSize = parseInt(document.getElementById("filter-page-size")?.value, 10) || 24;

    const veg = document.getElementById("filter-veg")?.checked;
    const vegan = document.getElementById("filter-vegan")?.checked;
    const jain = document.getElementById("filter-jain")?.checked;
    const satvik = document.getElementById("filter-satvik")?.checked;

    currentFilters = {
        page_size: pageSize,
        cuisine,
        meal_type: mealType,
        category,
        vegetarian: veg ? true : null,
        vegan: vegan ? true : null,
        jain: jain ? true : null,
        satvik: satvik ? true : null,
    };

    loadRecipes();
}

async function loadRecipes() {
    const statusContainer = document.getElementById("status-container");
    const grid = document.getElementById("recipes-grid");
    const pagination = document.getElementById("pagination");
    const btnPrev = document.getElementById("btn-prev-page");
    const btnNext = document.getElementById("btn-next-page");
    const pageIndicator = document.getElementById("page-indicator");

    grid.innerHTML = "";
    pagination.style.display = "none";
    statusContainer.innerHTML = `
        <div class="state-box">
            <div class="spinner"></div>
            <h3>Loading Recipes...</h3>
            <p>Fetching catalog from KitchenPilot backend.</p>
        </div>
    `;

    try {
        const params = {
            page: currentPage,
            ...currentFilters,
        };

        const data = await window.KitchenPilotApi.listRecipes(params);
        statusContainer.innerHTML = "";

        if (!data.recipes || data.recipes.length === 0) {
            statusContainer.innerHTML = `
                <div class="state-box">
                    <h3>No Recipes Found</h3>
                    <p>Try broadening your filter criteria or clearing dietary restrictions.</p>
                </div>
            `;
            return;
        }

        // Render Cards
        data.recipes.forEach((recipe) => {
            const card = document.createElement("div");
            card.className = "recipe-card";

            const vegBadge = recipe.vegetarian
                ? `<span class="badge badge-veg">Vegetarian</span>`
                : `<span class="badge badge-nonveg">Non-Veg</span>`;

            const cuisineBadge = recipe.cuisine
                ? `<span class="badge badge-cuisine">${escapeHtml(recipe.cuisine)}</span>`
                : "";

            const dietBadge = recipe.diet_type
                ? `<span class="badge badge-diet">${escapeHtml(recipe.diet_type)}</span>`
                : "";

            const totalTime = recipe.total_time_min ? `${recipe.total_time_min} mins` : "N/A";
            const servings = recipe.servings ? `${recipe.servings}` : "N/A";

            card.innerHTML = `
                <div>
                    <div class="card-header">
                        <h3>${escapeHtml(recipe.recipe_name)}</h3>
                    </div>
                    <div class="card-meta">
                        ${vegBadge}
                        ${cuisineBadge}
                        ${dietBadge}
                    </div>
                    <div class="card-body">
                        <div class="info-row">
                            <span>Meal Type:</span>
                            <strong>${escapeHtml(recipe.meal_type || "General")}</strong>
                        </div>
                        <div class="info-row">
                            <span>Total Time:</span>
                            <strong>${totalTime}</strong>
                        </div>
                        <div class="info-row">
                            <span>Servings:</span>
                            <strong>${servings}</strong>
                        </div>
                    </div>
                </div>
                <div class="card-footer">
                    <span style="font-size: 0.8rem; color: var(--text-light); font-weight: 600;">ID: ${escapeHtml(recipe.recipe_id)}</span>
                    <a href="recipe.html?recipe_id=${encodeURIComponent(recipe.recipe_id)}" class="btn btn-outline btn-sm">View Details &rarr;</a>
                </div>
            `;
            grid.appendChild(card);
        });

        // Update Pagination Controls
        if (data.total_pages > 1) {
            pagination.style.display = "flex";
            pageIndicator.textContent = `Page ${data.page} of ${data.total_pages} (${data.total.toLocaleString()} recipes)`;
            btnPrev.disabled = data.page <= 1;
            btnNext.disabled = data.page >= data.total_pages;
        }

    } catch (err) {
        statusContainer.innerHTML = `
            <div class="error-banner">
                <div>
                    <strong>Unable to load recipes:</strong> ${escapeHtml(err.message)}
                    <br><br>
                    <button class="btn btn-secondary btn-sm" onclick="loadRecipes()">Retry</button>
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
