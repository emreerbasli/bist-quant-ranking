# Phase A corrected data audit — EXP-DATA-001/002

## Gate result: PARTIAL

Price rows are mechanically usable for descriptive research, but remain `PROXY_UNVERIFIED` until listing/corporate-action provenance is reconciled. Fundamental and macro inputs are not eligible for model-selection evidence.

## Price evidence

- Symbols: 88; statuses: {'PROXY_UNVERIFIED': 88}.
- Sessions before each file's first bar: 35882; these are no longer called missing observations.
- Missing benchmark sessions between each symbol's first and last bar: 139.
- Zero/non-positive volume bars after first positive-volume bar: 1728.
- Absolute daily return flags above 50%: 5. They remain INVESTIGATE until split/bedelsiz provenance is verified.
- First bar is only a listing-date proxy, not an official IPO date.

## Fundamental, accounting and vintage evidence

- Records: 2646; fixed proxy schedule: 2646.
- Actual announcement timestamp coverage: 0.
- Vintage/restatement coverage: 0.
- Single-quarter/YTD/TTM basis coverage: 0.
- Market-cap fallback candidates: 190; records exposed to a later last-capital fallback: 190.

## Universe and macro evidence

- Historical universe/delist/listing candidate files found: 0.
- Current hard-coded universe present: True.
- Missing-month CPI fallback present: True.

## Acceptance

- Price-only descriptive baselines: CONTINUE with current-universe and corporate-action caveats.
- Fundamental/macro feature or model selection: INVESTIGATE; not accepted.
- V3/V4.1 and value/quality common-comparison baseline: N/A until inputs are verified.
