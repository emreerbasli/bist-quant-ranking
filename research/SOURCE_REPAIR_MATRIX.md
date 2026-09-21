# Source and repair matrix

| Area | Current evidence | Local repair possible | External source required | Research disposition |
|---|---|---|---|---|
| Price OHLCV | Local adjusted-looking Yahoo files with dividends/splits fields | Mechanical integrity and event flags | Authoritative corporate-action/listing reconciliation | PROXY_UNVERIFIED |
| Listing/delisting/universe | Current hard-coded ticker list | First-bar proxy only | Dated BIST membership/listing/delist archive | PROXY_UNVERIFIED; survivorship caveat |
| Fundamental values | 2,646 İş Yatırım current-snapshot records; exact KAP time/vintage absent | Raw balance and explicitly marked YTD proxy subsets | Filing-level KAP timestamps, first/corrected vintages and consolidation basis | PARTIAL: bounded PROXY research only |
| Accounting basis | Flow fields proven 3/6/9/12-month YTD; balance fields period-end | Same-period YTD comparison and point-balance subsets | Single-quarter decomposition, TTM and TFRS29 comparable-basis metadata | PARTIAL; legacy derived ratios INVALID |
| Market cap/capital | Tekil cache available; 190 no-prior-PD rows remeasured | 190 rows are pre-listing/no-price and remain missing; confirmed future-capital use 0 | Signal-date capital needed for rebuilt value features | Current carried value ratios INVALID; no proven stored future-capital contamination |
| CPI/policy rate | Hard-coded values | Remove from eligible research scope | Release-dated, vintage-aware official series | INVESTIGATE |
| USDTRY | Local price series | Mechanical audit | Source provenance if used for verified claims | PROXY_UNVERIFIED |
| Liquidity | Local volume and adjusted price | Compute diagnostic ADV/zero-return metrics | Adjustment-consistent volume and spread/impact evidence | PROXY_UNVERIFIED |

No provider, package, or API installation is performed by this work package.
