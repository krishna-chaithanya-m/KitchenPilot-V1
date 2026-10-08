/**
 * KitchenPilot-V1 — Modern Frontend Authentication Controller (auth.js)
 *
 * Implements complete website authentication UX:
 * 1. Email/Password Registration with live password requirements and confirm password
 * 2. Login with email/password and Google Sign-In (GIS)
 * 3. Email Verification workflow with status display and resend option
 * 4. Forgot Password workflow (anti-enumeration safe)
 * 5. Password Reset workflow with token validation and requirements check
 * 6. Google Identity Services integration (gracefully disabled when not configured)
 * 7. Rate limit (HTTP 429) handling with interactive countdown timers
 */

(function () {
    // Current active mode: 'login' | 'register' | 'forgot' | 'reset' | 'verify'
    let activeMode = "login";
    let countdownInterval = null;

    /**
     * Validates password against security policy:
     * - Minimum 8 characters
     * - At least one uppercase letter
     * - At least one lowercase letter
     * - At least one digit
     * - At least one symbol
     */
    function validatePasswordPolicy(password) {
        const str = password || "";
        const minLength = str.length >= 8;
        const hasUpper = /[A-Z]/.test(str);
        const hasLower = /[a-z]/.test(str);
        const hasDigit = /[0-9]/.test(str);
        const hasSymbol = /[^A-Za-z0-9]/.test(str);
        const isValid = minLength && hasUpper && hasLower && hasDigit && hasSymbol;
        return {
            isValid,
            minLength,
            hasUpper,
            hasLower,
            hasDigit,
            hasSymbol,
        };
    }

    /**
     * Updates live password checklist UI elements.
     */
    function updatePasswordChecklist(password, containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const results = validatePasswordPolicy(password);

        function setReq(id, met) {
            const el = container.querySelector(`[data-req="${id}"]`);
            if (el) {
                if (met) {
                    el.classList.add("met");
                    el.classList.remove("unmet");
                    const icon = el.querySelector(".req-icon");
                    if (icon) icon.textContent = "✓";
                } else {
                    el.classList.remove("met");
                    el.classList.add("unmet");
                    const icon = el.querySelector(".req-icon");
                    if (icon) icon.textContent = "○";
                }
            }
        }

        setReq("length", results.minLength);
        setReq("uppercase", results.hasUpper);
        setReq("lowercase", results.hasLower);
        setReq("number", results.hasDigit);
        setReq("symbol", results.hasSymbol);

        return results.isValid;
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

    /**
     * Sets up interactive alert in the specified alert container.
     */
    function showAlert(containerId, type, message, retryAfter = null) {
        const container = document.getElementById(containerId);
        if (!container) return;

        clearInterval(countdownInterval);

        let icon = "ℹ️";
        let typeClass = "auth-alert-info";
        if (type === "error") {
            icon = "⚠️";
            typeClass = "auth-alert-error";
        } else if (type === "success") {
            icon = "✅";
            typeClass = "auth-alert-success";
        } else if (type === "warning") {
            icon = "⚡";
            typeClass = "auth-alert-warning";
        }

        const safeMessage = escapeHtml(message);

        if (retryAfter && retryAfter > 0) {
            let remaining = retryAfter;
            container.className = `auth-alert ${typeClass}`;
            container.innerHTML = `
                <span class="auth-alert-icon">${icon}</span>
                <div>
                    <div>${safeMessage}</div>
                    <div style="margin-top: 0.35rem; font-size: 0.82rem;">
                        Please wait <span class="countdown-badge" id="alert-countdown">${remaining}</span> seconds before requesting again.
                    </div>
                </div>
            `;
            container.style.display = "flex";

            countdownInterval = setInterval(() => {
                remaining -= 1;
                const countdownEl = document.getElementById("alert-countdown");
                if (countdownEl) {
                    countdownEl.textContent = String(remaining);
                }
                if (remaining <= 0) {
                    clearInterval(countdownInterval);
                    container.innerHTML = `
                        <span class="auth-alert-icon">ℹ️</span>
                        <div>Rate limit period has ended. You may now retry your request.</div>
                    `;
                    container.className = "auth-alert auth-alert-info";
                }
            }, 1000);
        } else {
            container.className = `auth-alert ${typeClass}`;
            container.innerHTML = `
                <span class="auth-alert-icon">${icon}</span>
                <div>${safeMessage}</div>
            `;
            container.style.display = "flex";
        }
    }

    function clearAlert(containerId) {
        clearInterval(countdownInterval);
        const container = document.getElementById(containerId);
        if (container) {
            container.style.display = "none";
            container.innerHTML = "";
        }
    }

    /**
     * Switches view mode between login, register, forgot, reset, and verify.
     */
    function switchMode(newMode) {
        activeMode = newMode;

        // Hide all views
        const views = document.querySelectorAll(".auth-view");
        views.forEach((v) => (v.style.display = "none"));

        // Clear any alerts
        clearAlert("auth-global-alert");

        // Update tab buttons if present
        const tabs = document.querySelectorAll(".auth-tab-btn");
        tabs.forEach((tab) => {
            if (tab.getAttribute("data-mode") === newMode) {
                tab.classList.add("active");
            } else {
                tab.classList.remove("active");
            }
        });

        const targetView = document.getElementById(`view-${newMode}`);
        if (targetView) {
            targetView.style.display = "block";
        }

        // Context-sensitive header adjustments
        const headerTitle = document.getElementById("auth-card-title");
        const headerSubtitle = document.getElementById("auth-card-subtitle");

        if (headerTitle && headerSubtitle) {
            if (newMode === "login") {
                headerTitle.textContent = "Welcome Back";
                headerSubtitle.textContent = "Sign in to access your saved recipes, pantry, and personalized recommendations.";
            } else if (newMode === "register") {
                headerTitle.textContent = "Create Pilot Account";
                headerSubtitle.textContent = "Register to participate in the KitchenPilot-V1 personalized recipe evaluation.";
            } else if (newMode === "forgot") {
                headerTitle.textContent = "Reset Password";
                headerSubtitle.textContent = "Enter your account email to receive secure password recovery instructions.";
            } else if (newMode === "reset") {
                headerTitle.textContent = "Set New Password";
                headerSubtitle.textContent = "Choose a strong password meeting all security requirements.";
            } else if (newMode === "verify") {
                headerTitle.textContent = "Email Verification";
                headerSubtitle.textContent = "Confirm your email address to activate all account recovery features.";
            }
        }
    }

    /**
     * Initializes Google Identity Services if configured.
     */
    function initGoogleAuth() {
        const googleConfig = (typeof window.getGoogleAuthConfig === "function")
            ? window.getGoogleAuthConfig()
            : { enabled: false, clientId: "" };

        const googleButtons = document.querySelectorAll(".google-signin-btn-container");

        if (!googleConfig.enabled || !googleConfig.clientId) {
            // Google auth is disabled or not configured
            googleButtons.forEach((btnContainer) => {
                btnContainer.innerHTML = `
                    <button type="button" class="google-custom-btn" disabled title="Google Sign-In is not configured for this environment">
                        <svg width="18" height="18" viewBox="0 0 18 18">
                            <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.616z"/>
                            <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
                            <path fill="#FBBC05" d="M3.964 10.707c-.18-.54-.282-1.117-.282-1.707 0-.59.102-1.167.282-1.707V4.961H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z"/>
                            <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961L3.964 7.293C4.672 5.166 6.656 3.58 9 3.58z"/>
                        </svg>
                        <span>Continue with Google</span>
                    </button>
                    <div class="google-disabled-note">Google sign-in is disabled in this environment</div>
                `;
            });
            return;
        }

        // Google is enabled and has a valid client ID:
        // Dynamically load Google Identity Services if not yet loaded
        if (!window.google || !window.google.accounts) {
            const script = document.createElement("script");
            script.src = "https://accounts.google.com/gsi/client";
            script.async = true;
            script.defer = true;
            script.onload = () => setupGisClient(googleConfig.clientId);
            document.head.appendChild(script);
        } else {
            setupGisClient(googleConfig.clientId);
        }
    }

    /**
     * Initializes Google Identity Services client after script is loaded.
     */
    function setupGisClient(clientId) {
        if (!window.google || !window.google.accounts || !window.google.accounts.id) return;

        try {
            window.google.accounts.id.initialize({
                client_id: clientId,
                callback: handleGoogleCredentialResponse,
                auto_select: false,
                cancel_on_tap_outside: true,
            });

            const googleContainers = document.querySelectorAll(".google-signin-btn-container");
            googleContainers.forEach((container) => {
                container.innerHTML = "";
                window.google.accounts.id.renderButton(container, {
                    theme: "outline",
                    size: "large",
                    width: 380,
                    text: "continue_with",
                    shape: "rectangular",
                    logo_alignment: "left",
                });
            });
        } catch (e) {
            console.warn("Failed to initialize Google Identity Services:", e);
        }
    }

    /**
     * Handles credential returned by Google Identity Services.
     */
    async function handleGoogleCredentialResponse(response) {
        if (!response || !response.credential) {
            showAlert("auth-global-alert", "error", "Failed to retrieve Google credentials.");
            return;
        }

        clearAlert("auth-global-alert");
        const inviteCodeInput = document.getElementById("reg-invite-code");
        const inviteCode = inviteCodeInput ? inviteCodeInput.value.trim() : null;

        try {
            const authResult = await window.KitchenPilotApi.loginWithGoogle(response.credential, inviteCode || null);
            showAlert("auth-global-alert", "success", "Signed in with Google successfully! Redirecting...");
            setTimeout(() => {
                window.location.href = "recommendations.html";
            }, 800);
        } catch (err) {
            if (err.status === 403) {
                showAlert("auth-global-alert", "error", err.message || "Pilot cohort capacity reached or invite code required.");
            } else if (err.status === 429) {
                showAlert("auth-global-alert", "error", err.message, err.retryAfter);
            } else {
                showAlert("auth-global-alert", "error", err.message || "Google authentication failed.");
            }
        }
    }

    /**
     * Synchronizes pilot capacity and invite code requirements on registration form.
     */
    async function syncPilotStatus() {
        try {
            const status = await window.KitchenPilotApi.getPilotStatus();
            const inviteGroup = document.getElementById("group-reg-invite");
            const inviteInput = document.getElementById("reg-invite-code");
            const inviteLabel = document.getElementById("lbl-reg-invite");
            const regSubmitBtn = document.getElementById("btn-register-submit");

            if (status) {
                if (status.invite_code_required) {
                    if (inviteGroup) inviteGroup.style.display = "flex";
                    if (inviteLabel) inviteLabel.textContent = "Pilot Invite Code (Required)";
                    if (inviteInput) {
                        inviteInput.required = true;
                        inviteInput.placeholder = "Enter required invite code";
                    }
                } else {
                    if (inviteLabel) inviteLabel.textContent = "Pilot Invite Code (Optional)";
                    if (inviteInput) {
                        inviteInput.required = false;
                        inviteInput.placeholder = "Optional invite code";
                    }
                }

                if (status.available_slots <= 0) {
                    if (regSubmitBtn) {
                        regSubmitBtn.disabled = true;
                        regSubmitBtn.textContent = "Pilot Full (Registration Closed)";
                    }
                    showAlert(
                        "auth-global-alert",
                        "warning",
                        `The pilot cohort is currently full (${status.capacity}/${status.capacity} participants). Registration is temporarily closed, but existing users can still log in.`
                    );
                } else {
                    if (regSubmitBtn) {
                        regSubmitBtn.disabled = false;
                        regSubmitBtn.textContent = "Create Pilot Account";
                    }
                }
            }
        } catch (e) {
            console.warn("Could not retrieve pilot status:", e);
        }
    }

    /**
     * Initializes all event listeners and handles URL parameter-based routing.
     */
    function initAuth() {
        // Tab buttons
        const tabBtns = document.querySelectorAll(".auth-tab-btn");
        tabBtns.forEach((btn) => {
            btn.addEventListener("click", () => {
                const mode = btn.getAttribute("data-mode");
                switchMode(mode);
                if (mode === "register") {
                    syncPilotStatus();
                }
            });
        });

        // Quick navigation links within views
        document.querySelectorAll("[data-switch-mode]").forEach((el) => {
            el.addEventListener("click", (e) => {
                e.preventDefault();
                const mode = el.getAttribute("data-switch-mode");
                switchMode(mode);
                if (mode === "register") {
                    syncPilotStatus();
                }
            });
        });

        // Live password requirement checking for registration
        const regPassword = document.getElementById("reg-password");
        if (regPassword) {
            regPassword.addEventListener("input", () => {
                updatePasswordChecklist(regPassword.value, "reg-password-requirements");
            });
        }

        // Live password requirement checking for reset
        const resetPasswordInput = document.getElementById("reset-password");
        if (resetPasswordInput) {
            resetPasswordInput.addEventListener("input", () => {
                updatePasswordChecklist(resetPasswordInput.value, "reset-password-requirements");
            });
        }

        // 1. LOGIN FORM SUBMISSION
        const formLogin = document.getElementById("form-login");
        if (formLogin) {
            formLogin.addEventListener("submit", async (e) => {
                e.preventDefault();
                clearAlert("auth-global-alert");

                const email = document.getElementById("login-email").value.trim();
                const password = document.getElementById("login-password").value;
                const submitBtn = document.getElementById("btn-login-submit");

                if (!email || !password) {
                    showAlert("auth-global-alert", "error", "Please provide both email and password.");
                    return;
                }

                try {
                    if (submitBtn) submitBtn.disabled = true;
                    const res = await window.KitchenPilotApi.login(email, password);

                    // Check if email is unverified (non-blocking)
                    if (res && res.user && res.user.is_verified === false) {
                        showAlert(
                            "auth-global-alert",
                            "warning",
                            "Login successful! Note: Your email address is not yet verified. Please verify your email for secure account recovery."
                        );
                    } else {
                        showAlert("auth-global-alert", "success", "Login successful! Redirecting to recommendations...");
                    }

                    setTimeout(() => {
                        window.location.href = "recommendations.html";
                    }, 800);
                } catch (err) {
                    if (err.status === 429) {
                        showAlert("auth-global-alert", "error", err.message, err.retryAfter);
                    } else if (err.status === 401) {
                        showAlert("auth-global-alert", "error", "Invalid email or password. Please check your credentials.");
                    } else {
                        showAlert("auth-global-alert", "error", err.message || "Failed to sign in.");
                    }
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 2. REGISTRATION FORM SUBMISSION
        const formRegister = document.getElementById("form-register");
        if (formRegister) {
            formRegister.addEventListener("submit", async (e) => {
                e.preventDefault();
                clearAlert("auth-global-alert");

                const email = document.getElementById("reg-email").value.trim();
                const password = document.getElementById("reg-password").value;
                const confirmPassword = document.getElementById("reg-confirm-password").value;
                const displayName = document.getElementById("reg-display-name") ? document.getElementById("reg-display-name").value.trim() : null;
                const inviteCode = document.getElementById("reg-invite-code") ? document.getElementById("reg-invite-code").value.trim() : null;
                const submitBtn = document.getElementById("btn-register-submit");

                if (!email || !password || !confirmPassword) {
                    showAlert("auth-global-alert", "error", "Please fill in all required fields.");
                    return;
                }

                if (password !== confirmPassword) {
                    showAlert("auth-global-alert", "error", "Passwords do not match. Please verify your password confirmation.");
                    return;
                }

                const validation = validatePasswordPolicy(password);
                if (!validation.isValid) {
                    showAlert("auth-global-alert", "error", "Password does not satisfy all security requirements (minimum 8 characters, uppercase, lowercase, digit, and symbol).");
                    return;
                }

                try {
                    if (submitBtn) submitBtn.disabled = true;
                    const res = await window.KitchenPilotApi.register(email, password, displayName || null, inviteCode || null);

                    showAlert(
                        "auth-global-alert",
                        "success",
                        `Account created successfully! We have sent a verification email to ${email}. Please check your inbox and verify your email. Redirecting...`
                    );

                    setTimeout(() => {
                        window.location.href = "recommendations.html";
                    }, 1800);
                } catch (err) {
                    if (err.status === 429) {
                        showAlert("auth-global-alert", "error", err.message, err.retryAfter);
                    } else if (err.status === 409) {
                        showAlert("auth-global-alert", "error", "An account with this email address already exists.");
                    } else if (err.status === 403) {
                        showAlert("auth-global-alert", "error", err.message || "Registration closed or invalid invite code.");
                    } else {
                        showAlert("auth-global-alert", "error", err.message || "Failed to create account.");
                    }
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 3. FORGOT PASSWORD FORM SUBMISSION
        const formForgot = document.getElementById("form-forgot");
        if (formForgot) {
            formForgot.addEventListener("submit", async (e) => {
                e.preventDefault();
                clearAlert("auth-global-alert");

                const email = document.getElementById("forgot-email").value.trim();
                const submitBtn = document.getElementById("btn-forgot-submit");

                if (!email) {
                    showAlert("auth-global-alert", "error", "Please enter your account email address.");
                    return;
                }

                try {
                    if (submitBtn) submitBtn.disabled = true;
                    await window.KitchenPilotApi.forgotPassword(email);

                    // Anti-enumeration: Always show generic success
                    showAlert(
                        "auth-global-alert",
                        "success",
                        "If an account exists with that email address, password reset instructions have been sent. Please check your inbox and spam folder."
                    );
                    document.getElementById("forgot-email").value = "";
                } catch (err) {
                    if (err.status === 429) {
                        showAlert("auth-global-alert", "error", err.message, err.retryAfter);
                    } else {
                        // Even on network error, maintain safety
                        showAlert("auth-global-alert", "error", err.message || "Failed to request password reset.");
                    }
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 4. RESET PASSWORD FORM SUBMISSION
        const formReset = document.getElementById("form-reset");
        if (formReset) {
            formReset.addEventListener("submit", async (e) => {
                e.preventDefault();
                clearAlert("auth-global-alert");

                const tokenInput = document.getElementById("reset-token");
                const token = tokenInput ? tokenInput.value.trim() : "";
                const newPassword = document.getElementById("reset-password").value;
                const confirmPassword = document.getElementById("reset-confirm-password").value;
                const submitBtn = document.getElementById("btn-reset-submit");

                if (!token) {
                    showAlert("auth-global-alert", "error", "Reset token is missing. Please use the link provided in your recovery email.");
                    return;
                }

                if (!newPassword || !confirmPassword) {
                    showAlert("auth-global-alert", "error", "Please enter and confirm your new password.");
                    return;
                }

                if (newPassword !== confirmPassword) {
                    showAlert("auth-global-alert", "error", "New passwords do not match.");
                    return;
                }

                const validation = validatePasswordPolicy(newPassword);
                if (!validation.isValid) {
                    showAlert("auth-global-alert", "error", "New password does not satisfy all complexity requirements.");
                    return;
                }

                try {
                    if (submitBtn) submitBtn.disabled = true;
                    await window.KitchenPilotApi.resetPassword(token, newPassword);

                    showAlert(
                        "auth-global-alert",
                        "success",
                        "Password reset successful! You can now log in with your new password."
                    );

                    formReset.reset();
                    setTimeout(() => {
                        switchMode("login");
                    }, 2000);
                } catch (err) {
                    if (err.status === 429) {
                        showAlert("auth-global-alert", "error", err.message, err.retryAfter);
                    } else if (err.status === 400) {
                        showAlert("auth-global-alert", "error", "Invalid or expired password reset link. Please request a new reset email.");
                    } else {
                        showAlert("auth-global-alert", "error", err.message || "Failed to reset password.");
                    }
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 5. RESEND VERIFICATION FORM SUBMISSION
        const formResendVerification = document.getElementById("form-resend-verification");
        if (formResendVerification) {
            formResendVerification.addEventListener("submit", async (e) => {
                e.preventDefault();
                clearAlert("auth-global-alert");

                const email = document.getElementById("resend-email").value.trim();
                const submitBtn = document.getElementById("btn-resend-submit");

                if (!email) {
                    showAlert("auth-global-alert", "error", "Please enter your email address.");
                    return;
                }

                try {
                    if (submitBtn) submitBtn.disabled = true;
                    await window.KitchenPilotApi.resendVerification(email);

                    // Anti-enumeration: Generic safe message
                    showAlert(
                        "auth-global-alert",
                        "success",
                        "If the account exists and is unverified, a fresh verification email has been sent. Please check your inbox."
                    );
                    document.getElementById("resend-email").value = "";
                } catch (err) {
                    if (err.status === 429) {
                        showAlert("auth-global-alert", "error", err.message, err.retryAfter);
                    } else {
                        showAlert("auth-global-alert", "error", err.message || "Failed to resend verification email.");
                    }
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // URL Parameters & Hash Routing
        handleUrlRouting();

        // Initialize Google Sign-in
        initGoogleAuth();
    }

    /**
     * Reads URL query parameters or hash to automatically activate the intended screen.
     */
    async function handleUrlRouting() {
        const urlParams = new URLSearchParams(window.location.search);
        const hash = window.location.hash.replace("#", "");

        let targetMode = urlParams.get("mode") || hash || "login";
        const token = urlParams.get("token");

        // Specific detection for reset password or email verification
        if (window.location.pathname.includes("reset-password") || targetMode === "reset" || (token && urlParams.get("action") === "reset")) {
            targetMode = "reset";
            if (token) {
                const tokenInput = document.getElementById("reset-token");
                if (tokenInput) tokenInput.value = token;
            }
        } else if (window.location.pathname.includes("verify-email") || targetMode === "verify" || (token && !urlParams.get("action"))) {
            targetMode = "verify";
            if (token) {
                const tokenInput = document.getElementById("verify-token");
                if (tokenInput) tokenInput.value = token;
                // Automatically attempt verification with the token
                await triggerEmailVerification(token);
            }
        }

        switchMode(targetMode);

        if (targetMode === "register") {
            syncPilotStatus();
        }
    }

    /**
     * Executes email verification with the provided raw token.
     */
    async function triggerEmailVerification(token) {
        if (!token) return;

        const verifyStatusBox = document.getElementById("verify-status-box");
        if (verifyStatusBox) {
            verifyStatusBox.innerHTML = `
                <div class="spinner" style="width: 32px; height: 32px; margin: 1rem auto;"></div>
                <p style="text-align: center; color: var(--text-muted);">Verifying your email address with KitchenPilot backend...</p>
            `;
            verifyStatusBox.style.display = "block";
        }

        try {
            const res = await window.KitchenPilotApi.verifyEmail(token);

            // Update local user state if logged in
            const currentUser = window.KitchenPilotApi.getCurrentUser();
            if (currentUser) {
                currentUser.is_verified = true;
                localStorage.setItem("kitchenpilot_user", JSON.stringify(currentUser));
            }

            if (verifyStatusBox) {
                verifyStatusBox.innerHTML = `
                    <div class="auth-alert auth-alert-success" style="margin-bottom: 1rem;">
                        <span class="auth-alert-icon">✅</span>
                        <div>
                            <strong>Email Verified Successfully!</strong>
                            <p style="margin: 0.25rem 0 0 0;">Your email address has been verified. You now have full access to account recovery features.</p>
                        </div>
                    </div>
                    <div style="text-align: center; margin-top: 1rem;">
                        <a href="recommendations.html" class="btn btn-primary">Go to Recommendations 🚀</a>
                        <button type="button" class="btn btn-secondary" data-switch-mode="login" style="margin-left: 0.5rem;">Sign In</button>
                    </div>
                `;
            }
        } catch (err) {
            let errorMsg = "Verification link is invalid, expired, or has already been used.";
            if (err.status === 429) {
                errorMsg = err.message || "Too many verification requests. Please wait a moment.";
            }

            if (verifyStatusBox) {
                verifyStatusBox.innerHTML = `
                    <div class="auth-alert auth-alert-error" style="margin-bottom: 1rem;">
                        <span class="auth-alert-icon">⚠️</span>
                        <div>
                            <strong>Verification Failed</strong>
                            <p style="margin: 0.25rem 0 0 0;">${errorMsg}</p>
                        </div>
                    </div>
                    <p style="font-size: 0.88rem; color: var(--text-muted); margin-bottom: 0.75rem;">
                        Need a new verification link? Enter your email address below to receive a fresh verification link:
                    </p>
                `;
            }
        }
    }

    // Export utilities to window
    window.KitchenPilotAuth = {
        switchMode,
        validatePasswordPolicy,
        updatePasswordChecklist,
        showAlert,
        clearAlert,
        syncPilotStatus,
        initGoogleAuth,
        triggerEmailVerification,
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAuth);
    } else {
        initAuth();
    }
})();
