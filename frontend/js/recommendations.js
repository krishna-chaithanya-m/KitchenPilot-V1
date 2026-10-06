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

    // Setup Controlled Pilot controls (Stage J)
    setupPilotControls();
});

let currentAuthMode = "login"; // "login" | "register"

async function setupPilotControls() {
    const btnShowLogin = document.getElementById("btn-show-login");
    const btnShowRegister = document.getElementById("btn-show-register");
    const btnCancelAuth = document.getElementById("btn-cancel-auth");
    const btnSubmitAuth = document.getElementById("btn-submit-auth");
    const btnPilotLogout = document.getElementById("btn-pilot-logout");
    const btnLoadPantry = document.getElementById("btn-load-pantry");
    const btnSyncPrefs = document.getElementById("btn-sync-prefs");
    const btnPurgeData = document.getElementById("btn-purge-data");
    const btnDeactivateAcct = document.getElementById("btn-deactivate-acct");
    const authBox = document.getElementById("pilot-auth-box");
    const groupDisplayName = document.getElementById("group-display-name");
    const groupInviteCode = document.getElementById("group-invite-code");
    const authErrorMsg = document.getElementById("auth-error-msg");

    let pilotStatusInfo = null;

    async function syncPilotStatusUI() {
        try {
            pilotStatusInfo = await window.KitchenPilotApi.getPilotStatus();
            const lblInviteCode = document.getElementById("lbl-invite-code");
            const authInviteCode = document.getElementById("auth-invite-code");
            const helpInviteCode = document.getElementById("help-invite-code");

            if (pilotStatusInfo) {
                if (pilotStatusInfo.invite_code_required) {
                    if (lblInviteCode) lblInviteCode.textContent = "Invite Code (Required)";
                    if (authInviteCode) {
                        authInviteCode.placeholder = "Enter invite code";
                        authInviteCode.required = true;
                    }
                    if (helpInviteCode) helpInviteCode.textContent = "Issued by pilot administrator.";
                } else {
                    if (lblInviteCode) lblInviteCode.textContent = "Invite Code (Optional)";
                    if (authInviteCode) {
                        authInviteCode.placeholder = "Optional invite code";
                        authInviteCode.required = false;
                    }
                    if (helpInviteCode) helpInviteCode.textContent = "Optional for registration.";
                }

                if (pilotStatusInfo.available_slots <= 0) {
                    authErrorMsg.textContent = `Pilot cohort is currently full (${pilotStatusInfo.capacity}/${pilotStatusInfo.capacity}). Registration is closed.`;
                    authErrorMsg.style.display = "block";
                    if (btnSubmitAuth) btnSubmitAuth.disabled = true;
                } else {
                    if (btnSubmitAuth) btnSubmitAuth.disabled = false;
                }
            }
        } catch (err) {
            console.warn("Could not retrieve pilot status:", err);
        }
    }

    await updatePilotUI();
    await syncPilotStatusUI();

    if (btnShowLogin) {
        btnShowLogin.addEventListener("click", () => {
            currentAuthMode = "login";
            if (groupDisplayName) groupDisplayName.style.display = "none";
            if (groupInviteCode) groupInviteCode.style.display = "none";
            authErrorMsg.style.display = "none";
            authBox.style.display = "block";
        });
    }

    if (btnShowRegister) {
        btnShowRegister.addEventListener("click", async () => {
            currentAuthMode = "register";
            if (groupDisplayName) groupDisplayName.style.display = "block";
            if (groupInviteCode) groupInviteCode.style.display = "block";
            authErrorMsg.style.display = "none";
            authBox.style.display = "block";
            await syncPilotStatusUI();
        });
    }

    if (btnCancelAuth) {
        btnCancelAuth.addEventListener("click", () => {
            authBox.style.display = "none";
        });
    }

    if (btnSubmitAuth) {
        btnSubmitAuth.addEventListener("click", async () => {
            const email = document.getElementById("auth-email").value.trim();
            const password = document.getElementById("auth-password").value;
            const displayName = document.getElementById("auth-display-name") ? document.getElementById("auth-display-name").value.trim() : "";
            const inviteCode = document.getElementById("auth-invite-code") ? document.getElementById("auth-invite-code").value.trim() : "";

            authErrorMsg.style.display = "none";
            if (!email || !password) {
                authErrorMsg.textContent = "Email and password are required.";
                authErrorMsg.style.display = "block";
                return;
            }

            if (currentAuthMode === "register" && pilotStatusInfo && pilotStatusInfo.invite_code_required && !inviteCode) {
                authErrorMsg.textContent = "Pilot invite code is required. Please enter the invite code issued by your administrator.";
                authErrorMsg.style.display = "block";
                return;
            }

            try {
                if (currentAuthMode === "register") {
                    await window.KitchenPilotApi.register(email, password, displayName || null, inviteCode || null);
                } else {
                    await window.KitchenPilotApi.login(email, password);
                }
                authBox.style.display = "none";
                updatePilotUI();
            } catch (err) {
                authErrorMsg.textContent = err.message || "Authentication failed.";
                authErrorMsg.style.display = "block";
            }
        });
    }

    if (btnDeactivateAcct) {
        btnDeactivateAcct.addEventListener("click", async () => {
            if (confirm("Are you sure you want to deactivate your pilot participation? Your account will be disabled from logging in.")) {
                try {
                    await window.KitchenPilotApi.deactivateAccount();
                    alert("Your pilot participation has been deactivated.");
                    updatePilotUI();
                } catch (err) {
                    alert(err.message || "Failed to deactivate account.");
                }
            }
        });
    }

    if (btnPilotLogout) {
        btnPilotLogout.addEventListener("click", () => {
            window.KitchenPilotApi.logout();
            updatePilotUI();
        });
    }

    if (btnLoadPantry) {
        btnLoadPantry.addEventListener("click", async () => {
            try {
                const api = window.KitchenPilotApi;
                const pantry = await (api.getUserPantry ? api.getUserPantry() : api.getPantry());
                const items = Array.isArray(pantry) ? pantry : (pantry && pantry.items ? pantry.items : []);
                if (items && items.length > 0) {
                    const pantryNames = items.map(it => it.ingredient_name || it);
                    setIngredients(pantryNames);
                } else {
                    alert("Your pantry is currently empty. Add ingredients to your pantry or type them manually.");
                }
            } catch (err) {
                alert(err.message || "Failed to sync pantry.");
            }
        });
    }

    if (btnSyncPrefs) {
        btnSyncPrefs.addEventListener("click", async () => {
            const api = window.KitchenPilotApi;
            if (!api.isAuthenticated()) {
                alert("Please log in as a pilot participant before saving preferences.");
                return;
            }

            // Flush any typed text in the ingredient input box into ingredientsList
            const inputEl = document.getElementById("ingredient-input");
            if (inputEl && inputEl.value.trim()) {
                addIngredientFromInput();
            }

            const cuisine = document.getElementById("pref-cuisine").value.trim();
            const region = document.getElementById("pref-region").value.trim();
            const mealType = document.getElementById("pref-meal-type").value.trim();
            const category = document.getElementById("pref-category").value.trim();

            const userPrefs = {
                vegetarian: !!document.getElementById("pref-veg").checked,
                vegan: !!document.getElementById("pref-vegan").checked,
                jain: !!document.getElementById("pref-jain").checked,
                satvik: !!document.getElementById("pref-satvik").checked,
                preferred_cuisines: cuisine ? cuisine.split(",").map(c => c.trim()).filter(Boolean) : [],
                preferred_regions: region ? region.split(",").map(r => r.trim()).filter(Boolean) : [],
                preferred_meal_types: mealType ? mealType.split(",").map(m => m.trim()).filter(Boolean) : [],
                preferred_categories: category ? category.split(",").map(c => c.trim()).filter(Boolean) : [],
                preferred_ingredients: ingredientsList && ingredientsList.length > 0 ? [...ingredientsList] : [],
                cuisine: cuisine || null,
                region: region || null,
                meal_type: mealType || null,
                category: category || null,
            };

            const nutTargets = {};
            const maxCal = parseFloat(document.getElementById("nut-max-cal").value);
            if (!isNaN(maxCal) && maxCal >= 0) nutTargets.max_calories = maxCal;

            const minProt = parseFloat(document.getElementById("nut-min-prot").value);
            if (!isNaN(minProt) && minProt >= 0) nutTargets.min_protein = minProt;

            const maxFat = parseFloat(document.getElementById("nut-max-fat").value);
            if (!isNaN(maxFat) && maxFat >= 0) nutTargets.max_fat = maxFat;

            const maxCarbs = parseFloat(document.getElementById("nut-max-carbs").value);
            if (!isNaN(maxCarbs) && maxCarbs >= 0) nutTargets.max_carbs = maxCarbs;

            const minFiber = parseFloat(document.getElementById("nut-min-fiber").value);
            if (!isNaN(minFiber) && minFiber >= 0) nutTargets.min_fiber = minFiber;

            try {
                // 1. Update dietary, regional, cuisine, and preferred ingredients
                const updateFn = api.updatePreferences || api.updateUserPreferences;
                await updateFn(userPrefs);

                // 2. Update nutrition targets if provided
                if (Object.keys(nutTargets).length > 0) {
                    const updateNutFn = api.updateNutritionTargets || api.updateUserNutritionTargets;
                    if (updateNutFn) {
                        await updateNutFn(nutTargets);
                    }
                }

                // 3. Fully synchronize pantry inventory with current ingredientsList:
                const syncFn = api.syncUserPantry || api.syncPantry;
                if (syncFn) {
                    await syncFn(ingredientsList);
                } else if (api.addPantryItem) {
                    const existingPantry = await (api.getUserPantry ? api.getUserPantry() : api.getPantry());
                    const existingItems = Array.isArray(existingPantry) ? existingPantry : (existingPantry && existingPantry.items ? existingPantry.items : []);
                    const targetSet = new Set(ingredientsList.map(i => i.trim().toLowerCase()));
                    if (api.deletePantryItem) {
                        for (const it of existingItems) {
                            if (!targetSet.has((it.ingredient_name || "").trim().toLowerCase())) {
                                await api.deletePantryItem(it.id);
                            }
                        }
                    }
                    for (const ing of ingredientsList) {
                        await api.addPantryItem({ ingredient_name: ing, status: "IN_STOCK" });
                    }
                }

                alert("Preferences successfully saved to your pilot profile!");
            } catch (err) {
                alert(err.message || "Failed to save preferences.");
            }
        });
    }

    if (btnPurgeData) {
        btnPurgeData.addEventListener("click", async () => {
            if (confirm("Are you sure you want to permanently delete all your preferences, nutrition targets, pantry items, recommendation history, and feedback? This cannot be undone.")) {
                try {
                    await window.KitchenPilotApi.purgeUserData(false);
                    alert("Your personal data has been completely erased in compliance with privacy retention guidelines.");
                    setIngredients([]);
                } catch (err) {
                    alert(err.message || "Failed to purge user data.");
                }
            }
        });
    }
}

async function updatePilotUI() {
    const isAuthed = window.KitchenPilotApi.isAuthenticated();
    const userStatus = document.getElementById("pilot-user-status");
    const userDesc = document.getElementById("pilot-user-desc");
    const authActions = document.getElementById("pilot-auth-actions");
    const userControls = document.getElementById("pilot-user-controls");

    if (isAuthed) {
        if (userStatus) userStatus.textContent = "Active Session: Authenticated Pilot Participant";
        if (userDesc) userDesc.textContent = "Personalization active. Feedback and queries are securely linked to your isolated pilot profile.";
        if (authActions) authActions.style.display = "none";
        if (userControls) userControls.style.display = "flex";
        await loadUserPreferencesIntoForm();
    } else {
        if (userStatus) userStatus.textContent = "Active Session: Visitor (Anonymous Mode)";
        if (userDesc) userDesc.textContent = "Log in or register to synchronize pantry items, personalize recommendations, and record real-world interaction feedback.";
        if (authActions) authActions.style.display = "flex";
        if (userControls) userControls.style.display = "none";
    }
}

async function loadUserPreferencesIntoForm() {
    if (!window.KitchenPilotApi || !window.KitchenPilotApi.isAuthenticated()) return;
    try {
        const api = window.KitchenPilotApi;

        // 1. Sync pantry from backend if authenticated and form is empty
        if (ingredientsList.length === 0) {
            const pantry = await (api.getUserPantry ? api.getUserPantry() : api.getPantry());
            const items = Array.isArray(pantry) ? pantry : (pantry && pantry.items ? pantry.items : []);
            if (items && items.length > 0) {
                const pantryNames = items.map(it => it.ingredient_name || it);
                setIngredients(pantryNames);
            }
        }

        const profile = await window.KitchenPilotApi.getUserProfile();
        if (profile && profile.preferences) {
            const p = profile.preferences;
            const prefVeg = document.getElementById("pref-veg");
            const prefVegan = document.getElementById("pref-vegan");
            const prefJain = document.getElementById("pref-jain");
            const prefSatvik = document.getElementById("pref-satvik");
            if (prefVeg && p.vegetarian) prefVeg.checked = true;
            if (prefVegan && p.vegan) prefVegan.checked = true;
            if (prefJain && p.jain) prefJain.checked = true;
            if (prefSatvik && p.satvik) prefSatvik.checked = true;

            const prefCuisine = document.getElementById("pref-cuisine");
            if (prefCuisine && !prefCuisine.value && p.preferred_cuisines && p.preferred_cuisines.length > 0) {
                prefCuisine.value = p.preferred_cuisines.join(", ");
            }
            const prefRegion = document.getElementById("pref-region");
            if (prefRegion && !prefRegion.value && p.preferred_regions && p.preferred_regions.length > 0) {
                prefRegion.value = p.preferred_regions.join(", ");
            }
            const prefMealType = document.getElementById("pref-meal-type");
            if (prefMealType && !prefMealType.value && p.preferred_meal_types && p.preferred_meal_types.length > 0) {
                prefMealType.value = p.preferred_meal_types.join(", ");
            }
            const prefCategory = document.getElementById("pref-category");
            if (prefCategory && !prefCategory.value && p.preferred_categories && p.preferred_categories.length > 0) {
                prefCategory.value = p.preferred_categories.join(", ");
            }
        }
        if (profile && profile.nutrition_targets) {
            const nt = profile.nutrition_targets;
            const nutMaxCal = document.getElementById("nut-max-cal");
            if (nutMaxCal && !nutMaxCal.value && nt.max_calories != null) nutMaxCal.value = nt.max_calories;
            const nutMinProt = document.getElementById("nut-min-prot");
            if (nutMinProt && !nutMinProt.value && nt.min_protein != null) nutMinProt.value = nt.min_protein;
            const nutMaxFat = document.getElementById("nut-max-fat");
            if (nutMaxFat && !nutMaxFat.value && nt.max_fat != null) nutMaxFat.value = nt.max_fat;
            const nutMaxCarbs = document.getElementById("nut-max-carbs");
            if (nutMaxCarbs && !nutMaxCarbs.value && nt.max_carbs != null) nutMaxCarbs.value = nt.max_carbs;
            const nutMinFiber = document.getElementById("nut-min-fiber");
            if (nutMinFiber && !nutMinFiber.value && nt.min_fiber != null) nutMinFiber.value = nt.min_fiber;
        }
    } catch (err) {
        console.warn("Could not load user profile preferences:", err);
    }
}


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

    // Flush any typed text in the ingredient input box into ingredientsList
    const inputEl = document.getElementById("ingredient-input");
    if (inputEl && inputEl.value.trim()) {
        addIngredientFromInput();
    }

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
            renderZeroResultDiagnostics(data.diagnostics, statusContainer);
            return;
        }

        // Show header
        resultsHeader.style.display = "block";
        resultsMeta.textContent = `Found ${data.count} personalized recipes matching your pantry criteria (Top ${topK} ranked).`;

        const sessionId = data.session_id || ("sess_" + Date.now());

        // Explicitly record genuine IMPRESSION events when recommendations are rendered for an authenticated pilot user
        if (window.KitchenPilotApi.isAuthenticated()) {
            data.recommendations.forEach(item => {
                window.KitchenPilotApi.submitFeedback(item.recipe_id, "IMPRESSION", null, null, sessionId).catch(() => {});
            });
        }

        // Render Recommendation Cards
        data.recommendations.forEach((item) => {
            const card = document.createElement("div");
            card.className = "recipe-card";

            const matchedTags = item.matched_ingredients && item.matched_ingredients.length > 0
                ? item.matched_ingredients.map(m => `<span class="tag-matched">✓ ${escapeHtml(m)}</span>`).join(" ")
                : `<span style="font-size: 0.8rem; color: var(--text-light);">None from available list</span>`;

            const missingTags = item.missing_ingredients && item.missing_ingredients.length > 0
                ? item.missing_ingredients.slice(0, 4).map(m => `<span class="tag-missing">+ ${escapeHtml(m)}</span>`).join(" ")
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

                <div class="card-footer" style="flex-direction: column; gap: 0.5rem; align-items: stretch;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.8rem; color: var(--text-light); font-weight: 600;">ID: ${escapeHtml(item.recipe_id)}</span>
                        <a href="recipe.html?recipe_id=${encodeURIComponent(item.recipe_id)}" class="btn btn-outline btn-sm">View Full Recipe &rarr;</a>
                    </div>
                    <div class="feedback-actions" style="display: flex; gap: 0.35rem; justify-content: flex-end; padding-top: 0.35rem; border-top: 1px solid var(--border-color, #e5e7eb);">
                        <button type="button" class="btn btn-sm btn-fb" data-rid="${escapeHtml(item.recipe_id)}" data-type="LIKE" title="Like Recipe" style="font-size: 0.8rem; padding: 0.2rem 0.45rem;">👍 Like</button>
                        <button type="button" class="btn btn-sm btn-fb" data-rid="${escapeHtml(item.recipe_id)}" data-type="SAVE" title="Save Favorite" style="font-size: 0.8rem; padding: 0.2rem 0.45rem;">⭐ Save</button>
                        <button type="button" class="btn btn-sm btn-fb" data-rid="${escapeHtml(item.recipe_id)}" data-type="COOKED" title="Mark Cooked" style="font-size: 0.8rem; padding: 0.2rem 0.45rem;">🍳 Cooked</button>
                        <button type="button" class="btn btn-sm btn-fb" data-rid="${escapeHtml(item.recipe_id)}" data-type="DISLIKE" title="Dislike Recipe" style="font-size: 0.8rem; padding: 0.2rem 0.45rem;">👎 Dislike</button>
                        <button type="button" class="btn btn-sm btn-fb" data-rid="${escapeHtml(item.recipe_id)}" data-type="HIDE" title="Hide Recipe" style="font-size: 0.8rem; padding: 0.2rem 0.45rem;">👁️ Hide</button>
                        <button type="button" class="btn btn-sm btn-qual-fb" data-rid="${escapeHtml(item.recipe_id)}" title="Report Issue / Feedback">💬 Issue</button>
                    </div>
                </div>
            `;
            grid.appendChild(card);
        });

        // Attach feedback button click handlers
        grid.querySelectorAll(".btn-fb").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const rid = btn.getAttribute("data-rid");
                const ftype = btn.getAttribute("data-type");
                try {
                    await window.KitchenPilotApi.submitFeedback(rid, ftype, null, null, sessionId);
                    btn.style.background = "var(--badge-veg-bg)";
                    btn.style.color = "var(--badge-veg-text)";
                    btn.style.borderColor = "var(--badge-veg-border)";
                    btn.disabled = true;
                    btn.textContent = `✓ ${ftype}`;
                } catch (err) {
                    if (err.status === 401) {
                        alert("Please log in to record personalized recipe feedback.");
                    } else {
                        alert(err.message || "Failed to record feedback.");
                    }
                }
            });
        });

        // Attach qualitative feedback handlers
        grid.querySelectorAll(".btn-qual-fb").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const rid = btn.getAttribute("data-rid");
                const issueOptions = [
                    "recommendation_irrelevant",
                    "missing_ingredient",
                    "wrong_dietary_match",
                    "nutrition_information_issue",
                    "poor_explanation",
                    "slow_response",
                    "confusing_ui",
                    "useful_recommendation",
                    "other_issue"
                ];
                const choice = prompt(
                    `Report issue for this recommendation:\n\nSelect an issue type:\n${issueOptions.map((opt, i) => `${i+1}. ${opt}`).join("\n")}\n\nEnter number (1-9) or issue name:`,
                    "1"
                );
                if (!choice) return;

                let selectedIssue = choice.trim();
                const choiceIdx = parseInt(choice, 10);
                if (!isNaN(choiceIdx) && choiceIdx >= 1 && choiceIdx <= issueOptions.length) {
                    selectedIssue = issueOptions[choiceIdx - 1];
                } else if (!issueOptions.includes(selectedIssue)) {
                    selectedIssue = "other_issue";
                }

                const comments = prompt("Optional comments or details (what was unexpected?):", "");
                try {
                    await window.KitchenPilotApi.submitQualitativeFeedback(selectedIssue, comments, rid, sessionId);
                    btn.style.background = "var(--accent-indigo-light)";
                    btn.style.color = "var(--accent-indigo)";
                    btn.style.borderColor = "var(--accent-indigo)";
                    btn.textContent = "✓ Reported";
                    btn.disabled = true;
                } catch (err) {
                    if (err.status === 401) {
                        alert("Please log in to report qualitative feedback.");
                    } else {
                        alert(err.message || "Failed to submit qualitative feedback.");
                    }
                }
            });
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

function renderZeroResultDiagnostics(diagnostics, container) {
    if (!diagnostics) {
        container.innerHTML = `
            <div class="state-box">
                <h3>No Matching Recommendations</h3>
                <p>No catalog recipes satisfied your combined dietary filters and ingredient criteria. Try easing dietary restrictions or adding more common ingredients.</p>
            </div>
        `;
        return;
    }

    const cause = diagnostics.primary_cause || "constraint_conflict";
    const guidance = diagnostics.guidance || "No recipes satisfied your strict constraints.";
    const suggestions = diagnostics.safe_suggestions || [];
    const notice = diagnostics.constraint_preservation_notice || "Hard constraints were strictly enforced and never silently relaxed.";

    let suggestionsHtml = "";
    if (suggestions.length > 0) {
        suggestionsHtml = `
            <div class="safe-adjustments-box">
                <div style="font-weight: 700; font-size: 0.85rem; color: var(--secondary); margin-bottom: 0.5rem;">Recommended Safe Adjustments:</div>
                <ul style="margin: 0; padding-left: 1.25rem; font-size: 0.85rem; color: var(--text-muted);">
                    ${suggestions.map(s => `<li style="margin-bottom: 0.25rem;">${escapeHtml(s)}</li>`).join("")}
                </ul>
            </div>
        `;
    }

    container.innerHTML = `
        <div class="state-box state-box-warning">
            <div style="font-size: 1.75rem; margin-bottom: 0.5rem;">🛡️</div>
            <h3 style="margin-bottom: 0.25rem;">Zero Candidates Passed Hard Constraints</h3>
            <div class="state-warning-badge">
                Cause: ${escapeHtml(cause)}
            </div>
            <p style="max-width: 600px; margin: 0 auto 0.5rem auto; font-size: 0.95rem;">
                ${escapeHtml(guidance)}
            </p>
            ${suggestionsHtml}
            <div style="margin-top: 1rem; font-size: 0.75rem; color: var(--warning-title); font-style: italic;">
                ${escapeHtml(notice)}
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
