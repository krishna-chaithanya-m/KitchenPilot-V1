# KitchenPilot-V1 — Controlled Pilot Participant Notice & Consent (Stage K)

## 1. Overview & Purpose of the Pilot

Welcome to the **KitchenPilot-V1 Controlled Pilot**, developed under the *Customized AI Kitchen for India (Intel Unnati-3)* project. 

The objective of this pilot is to evaluate how real home cooks in India interact with personalized recipe recommendations, validate dietary and nutritional constraint safety, and collect trustworthy, genuine interaction signals to guide future machine learning models under the strictly gated Stage I ML lifecycle.

---

## 2. What the System Does

KitchenPilot-V1 provides:
- **Pantry-Aware Retrieval**: Recommendations tailored to ingredients currently available in your kitchen.
- **Strict Dietary Safety**: Guaranteed enforcement of vegetarian, vegan, Jain, satvik, and allergen exclusions *prior* to any machine learning ranking.
- **Nutrition Boundaries**: Filtering and ranking aligned with your target calorie, protein, carbohydrate, fat, and fiber goals.
- **Natural Language Explanations**: Transparent, deterministic explanations for why each dish was recommended.

---

## 3. What Data Is Collected & Why

To provide personalization and evaluate recommendation quality, the system stores:
1. **Account Credentials**: Your email and display name. Passwords are cryptographically hashed using salted bcrypt and are never visible to administrators.
2. **Culinary Preferences**: Dietary preferences, preferred regional cuisines, meal types, and ingredient affinities.
3. **Pantry Inventory**: Ingredients you add to your digital pantry and their stock levels.
4. **Interaction Feedback**: Explicit actions you take on recommended recipes:
   - **Impression**: Logged when a recommendation is rendered.
   - **Like / Save**: Signals positive preference for a dish.
   - **Cooked**: Signals that you prepared the dish.
   - **Dislike / Hide**: Signals negative preference or dish dismissal.
5. **Recommendation History**: Timestamps, query context, and scoring factors associated with recommendation sessions.

---

## 4. Non-Medical Disclaimer

> **IMPORTANT NOTICE**:
> **KitchenPilot-V1 is an experimental culinary AI recommendation prototype and is NOT a medical device, licensed dietitian, or clinical nutrition provider.**
> 
> - Nutritional estimates are calculated from standard food composition tables (CNF/Indian Food Composition) and are intended for general culinary guidance only.
> - The system does not diagnose, treat, prevent, or cure any medical condition.
> - If you have severe, life-threatening food allergies, medical dietary requirements (e.g., severe celiac disease, renal disease, diabetes management), or other clinical conditions, please verify all ingredients independently and consult a qualified healthcare professional.

---

## 5. Voluntary Participation & Right to Erasure

1. **Participation is Voluntary**: You may stop using the pilot at any time.
2. **Right to Complete Erasure**: In compliance with user data privacy standards, you can permanently delete all your personal data (preferences, pantry inventory, feedback, and recommendation history) at any time by clicking **"Purge My Data"** in the application interface or by calling `DELETE /api/v1/user/data`.
3. **Account Deactivation**: You may self-deactivate your pilot account at any time (`POST /api/v1/user/deactivate`), which immediately blocks all further authentication and access while preserving your option to purge data.
4. **No Third-Party Sharing**: Your data is stored on secure project infrastructure and is never sold, shared with advertising networks, or transmitted to third parties.

---

## 6. Pilot Invariants

- **Zero Fabricated Data**: No artificial or synthetic feedback will ever be generated or attributed to your account.
- **No Unsafe Constraint Relaxation**: Hard dietary and allergen constraints will never be silently relaxed to increase engagement.
- **No Unvetted Model Promotion**: Real user feedback is strictly governed by Stage I data sufficiency gates ($\ge 200$ interactions across $\ge 20$ users over $\ge 7$ days) before any candidate ranker can be trained and evaluated.
