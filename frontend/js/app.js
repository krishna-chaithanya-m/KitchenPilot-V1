/**
 * KitchenPilot-V1 — Home Page JavaScript (app.js)
 * Checks API connectivity and readiness status on page load.
 */

document.addEventListener("DOMContentLoaded", async () => {
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");

    if (!statusDot || !statusText) return;

    try {
        const health = await window.KitchenPilotApi.checkHealth();
        const ready = await window.KitchenPilotApi.checkReadiness();

        if (health.status === "ok" && ready.status === "ready") {
            statusDot.style.background = "var(--accent-emerald)";
            statusText.textContent = "Backend API & Recommendation Engine Ready";
            statusText.style.color = "var(--accent-emerald)";
        } else {
            statusDot.style.background = "var(--accent-amber)";
            statusText.textContent = "Backend Online (Model artifacts not ready)";
            statusText.style.color = "var(--accent-amber)";
        }
    } catch (err) {
        statusDot.style.background = "var(--danger)";
        statusText.textContent = "Backend Offline (FastAPI not reachable on port 8000)";
        statusText.style.color = "var(--danger)";
    }
});
