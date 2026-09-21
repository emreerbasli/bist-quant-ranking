# Isolated quantitative research

This directory is intentionally separate from `models/`, `bot/`, scheduled jobs,
and paper portfolios. Nothing here may overwrite a production model, cache, signal,
or portfolio state.

## Research protocol

1. Run Phase A before fitting or comparing a candidate.
2. Treat `2025-06-01` onward as contaminated historical evidence: it is descriptive
   only, never a selection holdout.
3. Follow the field × symbol × period evidence tiers in `MASTER_PLAN.md`.
   VERIFIED subsets can support decision experiments; PROXY/UNVERIFIED data
   support diagnostics only. The initial price `PASS` is not a PIT or price-
   accuracy certification.
4. Log every run in `EXPERIMENT_LEDGER.md`, including killed hypotheses.
5. A historical winner is a research candidate, not a production promotion.

`phase_a_data_audit.py` produces only research artifacts under
`research/results/`; it does not alter production data.

The initial EXP-A-001 is a preliminary scan, not completed Phase A. Its blanket
ledger disposition is historical; append a correction when implementation resumes.
No audit or experiment was rerun during the plan revision.

The governing plan is [MASTER_PLAN.md](MASTER_PLAN.md). Build the execution/label
contract and temporal validation infrastructure before feature/model selection.
This revision changes documentation only.
