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
            statusDot.style.background = "#10b981"; // Emerald green
            statusText.textContent = "Backend API & Recommendation Engine Ready";
            statusText.style.color = "#047857";
        } else {
            statusDot.style.background = "#f59e0b"; // Amber
            statusText.textContent = "Backend Online (Model artifacts not ready)";
            statusText.style.color = "#b45309";
        }
    } catch (err) {
        statusDot.style.background = "#ef4444"; // Red
        statusText.textContent = "Backend Offline (FastAPI not reachable on port 8000)";
        statusText.style.color = "#b91c1c";
    }
});
