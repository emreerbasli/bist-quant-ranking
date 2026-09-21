# EXP-FINAL-001 — PARETO FINALIST DECISION

## 1. Executive Summary

Phase J: **PASS**. **BOTH NON-DOMINATED**; **BOTH FINALISTS CARRIED FORWARD**.

## 2. Locked Decision Contract

`exp_final_001.json` locked before synthesis; no numeric score or weights.

## 3. Evidence Sources

| path | sha256 |
|---|---|
| results\EXP-MODEL-001_architecture_summary.csv | b393c3c81b37f21a57a5d82c7a3c424146f01d66cca9c28b0871dd2946f22995 |
| results\EXP-MODEL-001_classification.csv | 7c2507919c9b19511edf90e9afa69acbdd694220f810d34d3536a178b275410e |
| results\EXP-PORT-001_classification.csv | cbfff77296198015b417c838109fd31c838b16db7a276833b2d7c36296939c31 |
| results\EXP-PORT-001_cost_summary.csv | a565df943416cbdc58a65a4549980b811ed6b95a87af6fd89d7af1e0c0dc502f |
| results\EXP-PORT-001_delay_summary.csv | baa48a2c1f786a88be6a54c122b89ff75bcc8404a18157a2bf7e281c384ad98f |
| results\EXP-PORT-001_capacity_summary.csv | 7ab8a090476ff3040809db1da02a66ca4c99e6d393e144f151af816bb2df5d61 |
| results\EXP-ROBUST-001_classification.csv | e36358ccd9e3c502c0d72031033998691cbe886daac428100ed6de10cd8a485d |
| results\EXP-ROBUST-001_concentration.csv | 88854308792a5c09d2e25fa42310827f320afb782ca82c2ef6b9858919b3808a |
| results\EXP-ROBUST-001_leave_one_period_out.csv | be24c182445fc2a42e25fac849c2355304e98154f36a2cd353ccd291d06a7bd7 |
| results\EXP-ROBUST-001_bootstrap.csv | c3796bdaf04d2485801b48fa5631fa721d1abeb7174b401d8ca8772f854fb58a |
| results\EXP-ROBUST-001_ranking_similarity.csv | 9b02eb58b3f9dc3f06791dbcb5394ee0daf4064d661a882c662d7bc7c3e75058 |
| contracts\exp_model_001.json | 4f6b1a38345ad958d4e7869cc221e9f0e7caab9e0e7df3b75cac71ee06e9576d |
| contracts\exp_port_001.json | 6418537ab8006366b9022fd313d49f37ca2b3f26844d484cd92be4616fc22cd1 |
| contracts\exp_robust_001.json | 6e1b3b245c56e1451d23cf26381fc5322f8d5c4533f63d1ef89da2d16c7a8ae5 |

## 4. LGBM Regression Summary

| architecture | RETURN | RISK | ALPHA | STABILITY | COST | COMPLEXITY | DATA_QUALITY | hard_rejection | carry_forward | freeze_readiness |
|---|---|---|---|---|---|---|---|---|---|---|
| LGBM_REGRESSION | STRONG | STRONG | ACCEPTABLE | ACCEPTABLE | STRONG | STRONG | ACCEPTABLE | False | True | READY WITH CAVEATS |

## 5. LambdaMART Summary

| architecture | RETURN | RISK | ALPHA | STABILITY | COST | COMPLEXITY | DATA_QUALITY | hard_rejection | carry_forward | freeze_readiness |
|---|---|---|---|---|---|---|---|---|---|---|
| LAMBDAMART | STRONG | ACCEPTABLE | ACCEPTABLE | WEAK | STRONG | ACCEPTABLE | ACCEPTABLE | False | True | READY WITH CAVEATS |

## 6. RETURN

| architecture | RETURN |
|---|---|
| LGBM_REGRESSION | STRONG |
| LAMBDAMART | STRONG |

## 7. RISK

| architecture | RISK |
|---|---|
| LGBM_REGRESSION | STRONG |
| LAMBDAMART | ACCEPTABLE |

## 8. ALPHA

| architecture | ALPHA |
|---|---|
| LGBM_REGRESSION | ACCEPTABLE |
| LAMBDAMART | ACCEPTABLE |

## 9. STABILITY

| architecture | STABILITY |
|---|---|
| LGBM_REGRESSION | ACCEPTABLE |
| LAMBDAMART | WEAK |

## 10. COST

| architecture | COST |
|---|---|
| LGBM_REGRESSION | STRONG |
| LAMBDAMART | STRONG |

## 11. COMPLEXITY

| architecture | COMPLEXITY |
|---|---|
| LGBM_REGRESSION | STRONG |
| LAMBDAMART | ACCEPTABLE |

## 12. DATA QUALITY

| architecture | DATA_QUALITY |
|---|---|
| LGBM_REGRESSION | ACCEPTABLE |
| LAMBDAMART | ACCEPTABLE |

Shared: price PASS FOR RESEARCH, survivor-universe and provider caveats, three price features, macro/fundamental excluded.

## 13. Pareto Dominance

**BOTH NON-DOMINATED**. Regression has stronger controlled/bootstrapped alpha, drawdown, sector concentration and simplicity; LambdaMART has higher whole-procedure mean IC, positive-fold ratio, Sharpe and lower single-stock concentration. These are material tradeoffs.

## 14. Finalist Decision

**BOTH FINALISTS CARRIED FORWARD**. No hard rejection condition fired.

## 15. Ensemble Eligibility

**YES** — rank correlation 0.5575, Top-10 overlap 0.3786; no ensemble was built or backtested.

## 16. Freeze Readiness

| architecture | freeze_readiness |
|---|---|
| LGBM_REGRESSION | READY WITH CAVEATS |
| LAMBDAMART | READY WITH CAVEATS |

## 17. Known Caveats

Shared mom_63 dependence; Regression O1/time sensitivity and higher top-1 stock share; LambdaMART sector concentration and lower bootstrap P(IC>0); dependent folds/cohorts and shared data limitations.

## 18. Tests

8/8 dedicated Phase J tests and 136/136 full research regression tests PASS. Evidence hashes, no-fit/no-simulation boundary, no numeric score, Pareto rules and production scope were verified.

## 19. Production Integrity

Final protected-production hash verification: PASS, 0 changed.

## 20. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Because both finalists survive and ensemble justification is YES, review and authorize only optional Phase K rank-average ensemble experiment; do not build it automatically.
