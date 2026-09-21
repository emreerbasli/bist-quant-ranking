# EXP-DATA-005 — RESIDUAL PRICE RISK & MATERIALITY

## 1. Executive Summary

**PRICE DATA = PASS FOR RESEARCH.**  **PROVIDER-INDEPENDENT VERIFICATION = NOT
AVAILABLE.**  The 89-series, 159,229-row DATA-004 view was not rebuilt. A systematic
scan of the retained provider snapshot found one new early-adjustment error: KONTR's
nominal price basis changes on 2025-12-01 although the official 100% rights issue
starts on 2025-12-09. A research-only overlay quarantines the six intervening sessions
and reconnects the forward chain on the official ex-date. Production is unchanged.

After that control, 157,304 rows (98.7910%) are execution-eligible and 1,925
(1.2090%) are ineligible. Of the latter, 133 rows (0.0835%) are six known,
event-bounded quarantines; 1,792 rows (1.1254%) are generic unresolved observations.
No remaining unquarantined corporate-action pattern was found by the predeclared scan.
The remaining provider dependence is a caveat, not evidence that 157,298
`PROVIDER_ONLY` rows are corrupt.

## 2. Systematic Corporate-Action Scan

The detector used fixed data-quality thresholds, without looking at returns from a
strategy: absolute raw close discontinuity above 25%, absolute one-session
adjusted/raw ratio change above 0.5%, or a nonzero provider dividend/split field.
Across all 89 series it retained 526 distinct evidence rows:

| Test | Rows | Interpretation |
|---|---:|---|
| Provider dividend field | 443 | Evidence only, not official authority |
| Provider split field | 75 | Evidence only, not official authority |
| Adjusted/raw ratio jump | 383 | Every jump coincided with a dividend or split field |
| Ratio jump with both event fields empty | 0 | No D-pattern candidate |
| Absolute raw discontinuity >25% | 10 | Individually classified below |

The ten large discontinuities comprise five already controlled DATA-004 events, one
new KONTR event, two provider-declared HEKTS split sessions (2021-04-30 and
2022-10-12), and two 2020-03-12 cumulative gaps (ECILC/SELEC) immediately following
zero-volume stale marks. The latter two have no adjustment-ratio break and are handled
by the generic unavailable-mark policy; they are not classified as corporate actions.

## 3. Newly Found Candidate Events

Only KONTR 2025-12-01 survived as a new corporate-action candidate. Its raw close
falls from 33.40 to 17.181393 (-48.56%), both provider event fields are zero, and the
subsequent price basis remains near one half until the official action date. The six
sessions 2025-12-01 through 2025-12-08 are now
`PROVIDER_EARLY_ADJUSTMENT`/`UNRESOLVED` and not tradable. No other new candidate
requires external-source resolution.

## 4. Official Validation Results

Targeted KAP validation was performed only for KONTR. KAP notification 1524497,
published 2025-12-08, states a 100% rights issue at TRY 1.00 and a rights-use start of
2025-12-09. Borsa İstanbul's 2025-12-09 notice 1525040 gives the theoretical
post-action price as TRY 15.58. Therefore the provider's 2025-12-01 basis change is six
sessions early. The overlay uses announcement=2025-12-08,
effective/ex-date=2025-12-09, action=`RIGHTS_ISSUE`, ratio=1.0 and subscription
price=TRY 1.00. It does not rewrite any date before 2025-12-01.

Sources: <https://www.kap.org.tr/tr/Bildirim/1524497> and
<https://kap.org.tr/tr/Bildirim/1525040>.

## 5. Controlled Quarantine Materiality

The five DATA-004 events retain 127 quarantined rows. KONTR adds six, producing 133
rows across six tickers and six events. Every row is outside signal and execution
eligibility. Under the conservative label contract, any signal/label path touching one
of these rows is excluded: 253 dated paths for H=20, 362 for H=40 and 462 for H=60.
These rows are **controlled/quarantined risk**, not unknown data failures and are not
double-counted as residual material risk.

## 6. Missing Volume Materiality

There are 144 rows (0.0904% of the dataset) across six series: SASA 137, CANTE 2,
XU100 2, TCELL 1, TSKB 1 and YKBNK 1. All 144 retain a finite close, have a changing
OHLC range and have zero/missing volume; volume is never imputed. The rows form 44
streaks (median 2, 95th percentile 8, maximum 29); 65 rows have positive volume in an
immediately adjacent session. Year concentration is 2025=27 and 2026=112, with one
row each in 2018, 2019, 2020, 2022 and 2023.

On the existing 60-session diagnostic schedule, missing-volume rows intersect 4 of
2,329 possible signal dates and 3 of 2,327 possible next-session entries. Generic
positive-volume eligibility therefore bounds the problem without fabricating volume.

## 7. No-Trade/Stale Materiality

There are 1,646 unchanged-OHLC, zero-volume rows (1.0337%) across 88 series. They form
1,036 streaks: 766 one-session, 208 three-session, 60 four-session, one five-session
and one eleven-session streak (median 1, 95th percentile 4). All have finite prices;
1,305 have positive volume in an immediately adjacent session. Concentration is
strongly calendar-like: 2018=608, 2019=660 and the 2026-05-27/28/29 dates each contain
88 rows, consistent with common closed-session/stale marks rather than ticker-specific
action errors.

These rows cannot form signals or executions. On the existing diagnostic schedule
they intersect 61 signal dates and 59 next-session entry dates; an exit on the same
rebalance schedule has the same 59-date exposure. All 1,646 may require a last-valid
daily mark if a name is held. DATA-004's actual 50-bps control runs recorded 163 such
observations for equal weight and 27 for momentum; no fabricated execution occurred.

## 8. SASA Materiality

SASA has 2,201 rows. The provider volume defect accounts for 137 moving/ranged
zero-volume rows (25 in 2025, 112 in 2026); including three flat zero-volume rows,
the known defect population is 140/2,201 (6.36%). All generic unresolved causes
together remove 163 rows (7.41%) and create a maximum unresolved streak of 29.

On 33 scheduled control signal opportunities, the missing-volume defect blocks four
signals (12.1%) and three next-session entries (9.1%). SASA is therefore tagged
`MATERIALLY_PROBLEMATIC`, but not excluded: valid rows remain 2,038 and the generic
positive-volume/path policy contains the defect without a ticker-specific repair.

## 9. Provider-Only Risk Interpretation

`PROVIDER_ONLY` means that the retained value lacks an independent second-source
historical OHLCV verification. It does not mean the price is known to be wrong. The
risk taxonomy after DATA-005 is:

- **KNOWN SYSTEMATIC CORRUPTION:** six early provider adjustments identified.
- **CONTROLLED / QUARANTINED RISK:** all 133 associated sessions excluded and official
  ex-dates forward-reconnected.
- **UNVERIFIED PROVIDER DEPENDENCE:** 157,298 rows, explicitly caveated.
- **UNRESOLVED MATERIAL RISK:** 1,792 generic rows, measured and excluded by policy;
  concentrated cases are exposed in the ticker materiality table.

No known unquarantined systematic corporate-action corruption remains. Building a
full independent BIST archive is therefore not required to start controlled research.

## 10. Dataset Eligibility Coverage

| Measure | Rows | Dataset share |
|---|---:|---:|
| Total | 159,229 | 100.0000% |
| Eligible | 157,304 | 98.7910% |
| Ineligible | 1,925 | 1.2090% |
| Controlled quarantine (subset of ineligible) | 133 | 0.0835% |
| Unknown/generic unresolved (subset of ineligible) | 1,792 | 1.1254% |
| Provider-only (verification dimension) | 157,298 | 98.7873% |

Ticker/series bands use fixed coverage controls: zero unresolved rows is fully usable;
at most 2% loss and no run above five sessions is small loss; larger loss/run is
material; above 20% loss or fewer than 252 eligible rows is exclusion. Results are 0
fully usable, 82 small-loss, 7 materially problematic (KBORU, SASA, ASELS, CCOLA,
HEKTS, BSOKE, KONTR), and 0 excluded. KBORU's 17.36% is primarily the already known
104-session quarantine, not residual unknown corruption.

The two bad-OHLC observations are MIATK and MTRKS on 2022-06-27. Both remain
`UNRESOLVED_BAD_OHLC`, are ineligible, and represent 0.00126% of the dataset. No
special repair or broader investigation is warranted.

## 11. H=20/40/60 Coverage Diagnostic (NO PERFORMANCE)

The diagnostic requires 252 accumulated valid observations, at least 20 valid rows in
the last 25 sessions, a tradable signal and exit, and no `UNRESOLVED` row anywhere in
the signal-to-label-end path. It calculates no return, IC, Sharpe or model metric.

| H (sessions) | Candidate observations | Usable | Excluded | Coverage |
|---:|---:|---:|---:|---:|
| 20 | 131,157 | 121,704 | 9,453 | 92.7926% |
| 40 | 129,419 | 114,652 | 14,767 | 88.5898% |
| 60 | 127,681 | 108,239 | 19,442 | 84.7730% |

Longer paths naturally intersect more unavailable rows. These counts do not select a
horizon and must not be used as model-performance evidence.

## 12. Conservative Research Policy

The existing `PRICE_DATA_POLICY` remains sufficient and is applied as follows:

- unresolved signal, entry or exit price: exclude / do not fill;
- any unresolved or corporate-action-quarantine row in the configured label path:
  exclude the observation and record the cause;
- invalid OHLC: exclude;
- missing/nonpositive volume on a signal or execution date: not tradable; never impute;
- temporary no-trade held position: last-valid daily mark, no fabricated execution,
  reopening gap recognized at the next valid mark;
- provider action fields are evidence only; official ex-date controls any curated
  reconstruction; future events never rewrite past observations.

No new strategy, target, holding, rebalance or performance policy was introduced.

## 13. Remaining Material Risks

Independent raw OHLCV verification, complete official trading-status/action masters,
historical universe membership and listing/delisting provenance remain unavailable.
SASA and the other six material-coverage series require explicit coverage reporting in
later experiments. These limitations affect external validity and sample size but no
longer prevent conservative price-label construction.

The DATA-004 baseline was not rerun: KONTR's newly quarantined interval begins in
December 2025, after the baseline's 2025-05 endpoint, and DATA-004 already used the
same conservative execution eligibility. A rerun could not change that comparison.

## 14. Tests

DATA-005 tests: **6/6 PASS**.

1. Candidate detector sanity and zero ratio-jump-without-event cases.
2. All five prior events remain detected and controlled.
3. Eligibility policy consistency.
4. H=20/40/60 count identity (`candidate = usable + excluded`).
5. No unresolved row is silently converted to eligible/verified.
6. KONTR quarantine/ex-date behavior and no future-event rewrite.

Syntax compilation passed. The previously completed DATA-004 19/19 result remains
unchanged; DATA-005 did not rebuild that base.

## 15. Production Integrity

`research/verify_production_hashes.py` reports **PASS, 0 changed protected files**.
All new code, contracts, overlay data, results and manifests are under `research/`.
Production models, loaders, portfolios and execution code were not modified.

## 16. FINAL PRICE DATA GATE

**PRICE DATA = PASS FOR RESEARCH**

**PROVIDER-INDEPENDENT VERIFICATION = NOT AVAILABLE**

Rationale: all identified systematic early adjustments are now quarantined; the new
KONTR case is officially dated and controlled; residual observations are small,
measured and conservatively excluded; H=20/40/60 retains 84.77%–92.79% strict-path
coverage; and no known systematic corruption remains capable of silently entering
price labels. This gate authorizes only research that obeys the stated conservative
contract. It does not certify the provider as independently authoritative.

## 17. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Remain in Phase A and execute the next unpassed gate: the fundamental/accounting
PIT-vintage work package (real KAP filing time, first-published versus restated values,
single-quarter/YTD/TTM and TFRS29 basis), with the experiment ledger updated before
any target, feature or model research. Stop here; do not start that package
automatically.
