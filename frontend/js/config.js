/**
 * KitchenPilot-V1 — Runtime API Environment Configuration
 *
 * Provides configurable backend targeting for development and production/pilot environments.
 *
 * Resolution Priority:
 * 1. URL Query Parameter (?env=dev|prod or ?apiUrl=https://...)
 * 2. LocalStorage override ("kitchenpilot_api_base_url")
 * 3. Pre-existing window.KITCHENPILOT_API_BASE_URL
 * 4. Default Target: Azure Container Apps Production/Pilot Backend
 */

(function () {
    const ENVIRONMENTS = {
        production: "https://kitchenpilot-api.whitestone-ffca5e6e.malaysiawest.azurecontainerapps.io/api/v1",
        development: "http://127.0.0.1:8000/api/v1",
    };

    // Current default target configured for Pilot / Production testing:
    const DEFAULT_TARGET = ENVIRONMENTS.production;

    /**
     * Normalizes a given URL to ensure it has no trailing slash and includes /api/v1.
     * @param {string} rawUrl
     * @returns {string}
     */
    function normalizeApiUrl(rawUrl) {
        if (!rawUrl || typeof rawUrl !== "string") {
            return DEFAULT_TARGET;
        }
        let trimmed = rawUrl.trim().replace(/\/+$/, "");
        if (!trimmed.endsWith("/api/v1")) {
            trimmed = `${trimmed}/api/v1`;
        }
        return trimmed;
    }

    /**
     * Resolves the active backend API base URL from URL params, storage, or defaults.
     * @returns {string}
     */
    function resolveApiBaseUrl() {
        // 1. Check URL query parameters
        if (typeof window !== "undefined" && window.location && window.location.search) {
            try {
                const params = new URLSearchParams(window.location.search);
                const envParam = params.get("env");
                if (envParam) {
                    const normalizedEnv = envParam.toLowerCase();
                    if (normalizedEnv === "dev" || normalizedEnv === "development" || normalizedEnv === "local") {
                        if (typeof localStorage !== "undefined") {
                            localStorage.setItem("kitchenpilot_api_base_url", ENVIRONMENTS.development);
                        }
                        return ENVIRONMENTS.development;
                    }
                    if (normalizedEnv === "prod" || normalizedEnv === "production" || normalizedEnv === "azure") {
                        if (typeof localStorage !== "undefined") {
                            localStorage.setItem("kitchenpilot_api_base_url", ENVIRONMENTS.production);
                        }
                        return ENVIRONMENTS.production;
                    }
                }

                const customApi = params.get("apiUrl") || params.get("api_url") || params.get("api");
                if (customApi) {
                    const normalizedCustom = normalizeApiUrl(customApi);
                    if (typeof localStorage !== "undefined") {
                        localStorage.setItem("kitchenpilot_api_base_url", normalizedCustom);
                    }
                    return normalizedCustom;
                }
            } catch (e) {
                // Ignore search param parsing error
            }
        }

        // 2. Check localStorage override
        if (typeof localStorage !== "undefined") {
            try {
                const stored = localStorage.getItem("kitchenpilot_api_base_url");
                if (stored && stored.trim()) {
                    return normalizeApiUrl(stored);
                }
            } catch (e) {
                // Ignore localStorage security/access errors
            }
        }

        // 3. Check pre-existing window global
        if (typeof window !== "undefined" && window.KITCHENPILOT_API_BASE_URL) {
            return normalizeApiUrl(window.KITCHENPILOT_API_BASE_URL);
        }

        // 4. Default target
        return DEFAULT_TARGET;
    }

    const activeBaseUrl = resolveApiBaseUrl();

    // Export configuration and helper utilities to window
    if (typeof window !== "undefined") {
        window.KITCHENPILOT_ENVIRONMENTS = ENVIRONMENTS;
        window.KITCHENPILOT_API_BASE_URL = activeBaseUrl;

        /**
         * Programmatically set backend environment or custom URL.
         * @param {"production"|"development"|string} target
         */
        window.setKitchenPilotEnvironment = function (target) {
            let targetUrl;
            if (target === "dev" || target === "development" || target === "local") {
                targetUrl = ENVIRONMENTS.development;
            } else if (target === "prod" || target === "production" || target === "azure") {
                targetUrl = ENVIRONMENTS.production;
            } else {
                targetUrl = normalizeApiUrl(target);
            }
            if (typeof localStorage !== "undefined") {
                localStorage.setItem("kitchenpilot_api_base_url", targetUrl);
            }
            window.KITCHENPILOT_API_BASE_URL = targetUrl;
            console.info(`[KitchenPilot] API Base URL set to: ${targetUrl}`);
            return targetUrl;
        };

        /**
         * Clear overrides and reset to the default pilot/production environment.
         */
        window.resetKitchenPilotEnvironment = function () {
            if (typeof localStorage !== "undefined") {
                localStorage.removeItem("kitchenpilot_api_base_url");
            }
            window.KITCHENPILOT_API_BASE_URL = DEFAULT_TARGET;
            console.info(`[KitchenPilot] API Base URL reset to default: ${DEFAULT_TARGET}`);
            return DEFAULT_TARGET;
        };
    }
})();
