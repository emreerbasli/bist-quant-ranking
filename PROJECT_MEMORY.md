# PROJECT MEMORY — BIST Quant Research

Son güncelleme: 2026-09-19 (Europe/Istanbul)

Bu dosya projenin kısa, güncel operasyonel hafızasıdır. Ayrıntılı metodoloji için `research/MASTER_PLAN.md`, deney ve karar geçmişi için `research/EXPERIMENT_LEDGER.md` esas alınır.

## Kaynak rolleri

- `research/MASTER_PLAN.md`: metodoloji ve araştırma otoritesi.
- `research/EXPERIMENT_LEDGER.md`: deney, gate ve karar geçmişi otoritesi.
- `PROJECT_MEMORY.md`: güncel durum, kritik tarihçe ve operasyonel kurallar.
- Frozen candidate manifestleri: aday kimliği, model hashleri ve dondurulmuş config otoritesi.
- `research/forward_infrastructure/FORWARD_INFRASTRUCTURE_MANIFEST_V12.json`: aktif forward altyapı byte-set otoritesi.
- `research/forward_infrastructure/forward_activation.json`: controlled activation ve gerçek clean-forward başlangıç otoritesi.

## Current status

- Research phase: **COMPLETED**
- Freeze phase: **COMPLETED**
- Forward infrastructure audit: **PASSED WITH NON-MATERIAL CAVEATS**
- Controlled clean-forward activation: **COMPLETED**
- Clean-forward status: **ACTIVE**
- Production deployment: **NOT DONE**
- Current mode: **CLEAN-FORWARD SHADOW MONITORING**
- Production V3 remains isolated; shadow activation is not a production deployment.

## Frozen candidates

### RC-LGBMR-001

- Architecture: LGBM Regression
- Target / horizon: RAW / H60
- Features: `mom_12_1`, `mom_63`, `vol_63`
- Portfolio: K10, equal weight
- Version: 1.0.0
- Model SHA256: `350fb049f7f2e392a62fc89516acbb00676e1b1ef922559fc2f1dc3bfe9e81f6`

### RC-LAMBDAMART-001

- Architecture: LambdaMART
- Target / horizon: BETA_RESIDUAL / H60
- Features: `mom_12_1`, `mom_63`, `vol_63`
- Portfolio: K10, equal weight
- Version: 1.0.0
- Model SHA256: `4744a5109bc3f97b11f2ef6f890cdded5672fd5a25a9a8252f9e1ad7fb31d849`

Her iki aday aynı controlled activation ve aynı `CLEAN_FORWARD_START` zamanına bağlıdır. Candidate artifact veya config değişikliği yeni candidate/version ve yeni clean-forward clock gerektirir.

## Authoritative forward infrastructure

- Manifest: `FORWARD_INFRASTRUCTURE_MANIFEST_V12.json`
- SHA256: `95074644bc4879cea898dedde2905c96599955994a7863f9601fd9992fed1da3`
- Independent read-only audit: **AUDIT PASS WITH NON-MATERIAL CAVEATS**
- Material issues: **NONE**
- Final recorded evidence: dedicated operational classification suite 13/13 PASS; full research suite 277/277 PASS; candidate integrity PASS; protected production diff 0; official logs empty before activation.
- V8/V9/V10/V11 are historical remediation artifacts, not current runtime authority. Do not delete them when they are referenced by the audit/ledger trail.

## Clean-forward activation

- Activation: **PASS**
- Activation mode: `CLEAN_FORWARD_SHADOW`
- `CLEAN_FORWARD_START`: `2026-09-19T04:16:05.7473552+03:00`
- Activation source-max baseline: `2026-09-15`
- Activation baseline snapshot SHA256: `c7ea3304a5eb8aa47a69e45c9b7a90939b25ace4fd91300c1aa401db066b9fd5`
- Activation artifact SHA256: `15736826da9a43c88103bba7ae1451b5ad9594fb291389f8cb601f23cb1b30a6`
- Retroactive clean-forward evidence: **NONE**
- Official signal/portfolio/operational logs at activation: **EMPTY**
- Protected production integrity at activation: **UNCHANGED (diff 0)**
- Activation artifact is write-once/read-only and cryptographically binds V12, both candidate hashes, frozen target/horizon contracts, baseline snapshot and production isolation.

The model-freeze timestamp `2026-09-18T02:25:56.600962+03:00` is historical and is **not** `CLEAN_FORWARD_START`. Only the activation timestamp above is the real clean-forward beginning.

## Research conclusions

- Legacy V3 remains the frozen production benchmark/reference.
- V4 Raw was rejected; do not reopen the same raw approach.
- Price-only feature expansion failed under the locked experiment; the surviving frozen set is only `mom_12_1`, `mom_63`, `vol_63`.
- LGBM Regression and LambdaMART both survived the controlled research process; neither conclusively dominated.
- The fixed 50/50 rank-average ensemble was rejected for this cycle.
- No new model, feature, target, horizon or ensemble search is authorized during clean-forward monitoring unless a material defect is found or `MASTER_PLAN` explicitly requires it.
- Prediction horizon, rebalance frequency and holding period remain separate concepts. H60 here is the frozen candidate target horizon; it is not a general proof that 60 sessions is universally optimal.

## Critical historical remediation trail

Historical summary only; completed items are not current next actions:

- The initial forward runner was unsafe for clean prospective evidence.
- Activation and exact manifest authority were hardened; downgrade and mismatch paths fail closed.
- Transaction journaling, locking, semantic idempotency and restart behavior were hardened.
- Canonical and sandbox `RunnerDataSources` boundaries were added; official/sandbox mixing and path escape fail closed.
- Prospective calendar semantics and next-eligible-session pending execution were corrected.
- Incremental H60 cohort tracking was added; only completed configured-horizon cohorts enter metrics.
- Forward ADV20 was aligned with the frozen historical execution contract, including eligibility filtering and minimum 15 valid observations.
- Explicit SNAPSHOT and ORDER operational stages were added with `SNAPSHOT_HASH_FAILURE` and `ORDER_FAILURE` classifications.
- V12 is the final independently audited forward infrastructure authority.

## Clean-forward rules

1. Historical replay or backfill never counts as clean-forward evidence.
2. Data or signals at/before the activation source-max baseline never count as clean-forward evidence.
3. Only genuinely new eligible BIST sessions after the activation baseline may create official clean-forward evidence.
4. Do not change candidate models, features, targets, horizons, K, weighting or execution semantics during monitoring.
5. Do not select a winner from early forward observations.
6. H60 means 60 eligible post-signal sessions, not calendar days.
7. Pending cohorts do not enter completed-cohort metrics.
8. Overlapping cohorts are not independent observations.
9. A material candidate change requires a new candidate/version, independent approval and a new clean-forward clock.
10. Official signal/order/fill/NAV evidence must be generated only by the activation-gated frozen runner in its normal prospective flow.

## Known non-material limitations

- Survivor-universe limitation.
- Provider-dependent price history and volume.
- Only three price features.
- Material dependence on `mom_63` in historical robustness results.
- Macro and fundamental data are not used in the current frozen wave.
- Fundamental PIT/vintage readiness remained partial; unrecovered legacy data is not VERIFIED.
- Initial clean-forward evidence and completed H60 cohort counts will be small.
- Overlapping H60 cohorts limit effective independent sample size.

These limitations constrain interpretation; they are not current forward-infrastructure blockers.

## Production safety

- Production remains isolated; protected production diff at activation was 0.
- The clean-forward system is shadow monitoring, not deployment and not live order execution.
- Research/forward work must not mutate production V3, Telegram, scheduler, production signals/cache, model artifacts or paper portfolio.
- No automatic broker order connection is authorized.
- Existing production/UI history may remain in the repository, but it is not evidence for the frozen research candidates.

## Current next action

**Wait for genuinely new eligible BIST market data after the activation baseline and run the frozen prospective shadow runner normally.**

Do not open a new audit, regenerate V10/V11/V12, redo sandbox remediation, replay historical sessions, generate test signals or start a new research wave merely because more validation would be desirable.
