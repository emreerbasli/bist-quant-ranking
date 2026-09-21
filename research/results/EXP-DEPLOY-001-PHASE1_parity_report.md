# EXP-DEPLOY-001 — Phase 1 data bridge / canonical parity

## Result

**FAIL — do not proceed to Phase 2.**

The existing daily `data/raw` source cannot be used as a prospective extension of the frozen canonical research price-view without changing frozen data semantics.

## Controlled comparison

- As-of date: `2026-09-15`
- Universe: 88 symbols; SASA.IS was unavailable for the common usable feature set.
- Compared source: `data/raw/*.parquet` from the daily updater.
- Frozen reference: the V12 canonical price-view consumed by `CanonicalRunnerDataSources`.
- Candidate artifacts, V12-bound source, activation artifact and production files were not changed.

## Evidence

Across 157,058 common finite observations, daily raw versus frozen-provider values differed as follows:

| field | differing observations | maximum absolute difference |
| --- | ---: | ---: |
| open | 107,824 | 171.9766201613536 |
| high | 107,824 | 177.17216293871684 |
| low | 107,824 | 159.16511889260937 |
| close | 107,824 | 172.3228759765625 |
| volume | 10 | 2,873,286,022 |

The daily updater uses yfinance with `auto_adjust=True`, whereas the frozen view is built from a separate raw/adjusted provider snapshot and its locked corporate-action treatment. Therefore the two sources are not interchangeable.

Feature parity also failed at the frozen as-of date:

| feature | maximum absolute difference |
| --- | ---: |
| mom_12_1 | 1.8851285620000149 |
| mom_63 | 0.6080177052182336 |
| vol_63 | 0.051246834423744524 |

Candidate scoring results:

| candidate | score parity | Top-10 parity | Top-10 overlap |
| --- | --- | --- | ---: |
| RC-LGBMR-001 | FAIL; max score delta 0.3835911075526891 | FAIL | 9/10 |
| RC-LAMBDAMART-001 | FAIL; max score delta 0.4773986055240337 | FAIL | 9/10 |

## Decision

No data bridge, web integration, Telegram integration, scheduler migration or production-facing model change was created. Treating `data/raw` as a canonical extension would be a material data-semantic change and would invalidate the assumption that the current clean-forward clock remains comparable.

## Required resolution before retry

Provide or build an independently verified prospective source with the same raw/adjustment/corporate-action semantics as the frozen canonical view, then rerun this exact parity gate before any later phase.
