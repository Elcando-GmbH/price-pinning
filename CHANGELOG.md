# Changelog

## 0.1.0 — 2026-11-03

First public release.

- `check`: flag a stock as pinned when the 20-day median of absolute daily returns is at most 0.30 times the 252-day median, using only closes before the given day
- `pinning_frame`: the daily series behind the flag (ratio, short-window range, standard-deviation ratio)
- `pricepinning.filings`: reference implementation of D1 (takeover detection from SEC filings, rejected), kept to reproduce the evidence; not used by `check`
- docs/DECISIONS.md: D1 (takeover detection from SEC filings) rejected with evidence; D2 (price pinning) adopted with calibration, check on 3,958 series, alternatives tested against criteria set in advance, known limits
