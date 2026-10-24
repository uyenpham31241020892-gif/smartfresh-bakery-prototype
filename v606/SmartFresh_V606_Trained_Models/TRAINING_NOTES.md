# SmartFresh V6.06 — Training-only artifacts

Only ZIP 02 was read. M2 uses `day` target and a right-censored lower-bound asymmetric squared loss, selected on validation. X strictly follows the allowlist in `feature_contract.json`. M1 imitates logged baseline HOLD/markdown actions and separately forecasts next-30-minute observed sales under logged actions. It **does not** estimate causal discount uplift and is **not** an optimized discount policy.

Do not describe these artifacts as TEST-ready or POS-integrated. No 01/private, 03/test-runtime, 04 external data was accessed. No July/August data used, no official test, freeze, simulator adjustment, or profit claims. M2 fallbacks/OOD and M1 approval/price constraints must be enforced by a properly integrated future adapter/runtime before any test. Validation is development only.
