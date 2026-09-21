# EXP-A-001 — Data and leakage audit

**Disposition:** BLOCKED_FOR_FUNDAMENTAL_OR_MACRO_MODEL_SELECTION

- Price files: {'PASS': 88}
- Price flags: 1787 zero/non-positive-volume bars, 36021 constituent-date absences versus XU100, and 5 raw returns above 50% in absolute value.
- Fundamental files: {'WARN': 88}; fixed proxy validity dates: 2646
- Historical universe: BLOCKER (current-universe survivorship bias cannot be measured).
- PIT fundamentals: BLOCKER (the builder uses fixed release-lag dates, not actual KAP filing timestamps).
- Macro: BLOCKER (hard-coded CPI values plus a 2% fallback; no release calendar).
- Corporate actions: INVESTIGATE (adjustment provenance and event reconciliation absent).

Price-only descriptive baselines may proceed only with an explicit current-universe caveat. Feature/target/model selection that uses fundamental or macro inputs must wait for actual filing/release timestamps. See `EXP-A-001_data_audit.json` for symbol-level evidence.
