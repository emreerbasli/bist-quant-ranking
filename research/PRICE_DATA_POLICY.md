# Research price-data policy (EXP-DATA-003)

This policy applies only to artifacts under `research/`. It does not change the
production downloader, caches, models, or portfolios.

## Signal-date eligibility

A symbol is eligible only when all of the following are true on the signal date:

1. Open and close are finite and strictly positive; OHLC invariants hold within
   numeric tolerance.
2. At least 252 valid positive-volume observations exist up to the signal date.
3. At least 20 of the most recent 25 benchmark sessions have valid,
   positive-volume observations.
4. The signal-date close is not a carried mark and is not part of a flat,
   zero-volume stale run.
5. Liquidity evidence is observable: signal-date volume is positive and recent
   valid-volume coverage satisfies rule 3. No return-derived threshold is tuned.

These thresholds are data-integrity controls, not optimized strategy parameters.

## Missing, stale and suspended observations

- A held position is valued at its last valid close until a new valid mark exists.
  The reopening gap is recognized when that mark arrives. This is explicitly a
  valuation mark, not an assumed zero economic return.
- No future observation may fill or value an earlier date.
- A missing/stale position is never silently deleted.
- Entry and exit require a valid contemporaneous price and positive volume.
  Otherwise the order is logged as `trade not filled`; an untradeable existing
  position remains held and separately logged.
- Daily NAV retains cash for an unfilled new allocation rather than reallocating
  it across the other names.

## Corporate actions

- Official KAP/Borsa ex-dates and terms override provider-inferred event dates.
- A verified total-return adjusted series may embed splits/bonus issues and cash
  dividends. When it does, dividend cash is not added again.
- Rights issues require either (a) a verified total-return adjustment incorporating
  the subscription price/right value, or (b) explicit raw-price, cash and entitlement
  accounting. The two methods must never be combined.
- Raw and adjusted series, action terms and ex-dates must be retained separately.
- Provider `stock_splits`/`dividends` fields are evidence, not authority; missing
  fields do not prove that no action occurred.
- The EXP-DATA-003 reconciled view is a diagnostic total-return reconstruction. It
  neutralizes five false economic losses but does not claim authoritative raw-price
  reconstruction or overwrite production parquet files.

