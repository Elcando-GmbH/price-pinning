# price-pinning

[![CI](https://github.com/Elcando-GmbH/price-pinning/actions/workflows/ci.yml/badge.svg)](https://github.com/Elcando-GmbH/price-pinning/actions/workflows/ci.yml)

Detect stocks whose price has stopped moving, typically because a cash takeover offer pins it
to the offer price, from the price series alone.

After a cash offer, a stock's daily moves shrink to a fraction of their usual size while the
announcement premium stays in the trailing year. On its own history the stock then looks
unusually calm and unusually profitable, and what it really offers is a deal spread. Index
providers keep such a stock in the index until the deal closes. This package flags it without
event data, filings or manual judgement, so the same call works on the day and in a historical
study.

## The measure

```
ratio = median(|daily return|, last 20 days) / median(|daily return|, last 252 days)
```

computed from closes **before** the day in question. A ratio at or below 0.30 flags the stock
as pinned; the flag clears as soon as the ratio rises above 0.30. Medians, not standard
deviations, because a single announcement jump would hold a standard deviation up for weeks.

On 324 US large caps (2025–2026), two cash takeovers were flagged 9 and 14 trading days after
the announcement, while other stocks fell below the threshold on 0.017 % of stock-days. On
3,958 series back to 2000, 34 clear cases were flagged after a median of 11 trading days.
Decision log with the rejected filing-based approach, calibration, alternatives tested against criteria set in advance, and limits: [docs/DECISIONS.md](https://github.com/Elcando-GmbH/price-pinning/blob/main/docs/DECISIONS.md).

## Why not read the filings?

Detecting takeovers from SEC filings is the obvious approach, and it was tried first. On 324
US stocks it produced 36 flags, 31 of which needed a person to read the filing, and 2 of 5
stocks classified as targets were wrong. The reasons are in
[docs/DECISIONS.md](https://github.com/Elcando-GmbH/price-pinning/blob/main/docs/DECISIONS.md#d1--detect-pending-takeovers-from-sec-filings-rejected-2-nov-2026) (D1).
The filing reader that produced this evidence is included as `pricepinning.filings`
(`classify`, `cik_map`, `header_roles`): it reads a company's EDGAR submissions point in time
and tells target from acquirer by one-sided evidence. It downloads nothing; the caller passes
in the SEC JSON and headers. It is not used by the pinning flag.

## Install

```bash
pip install git+https://github.com/Elcando-GmbH/price-pinning.git
```

Python 3.11 or later. The only dependency is pandas.

## Use

```python
import datetime as dt
from pricepinning import check, pinning_frame

r = check("XYZ", closes, dt.date(2026, 11, 3))  # closes: pandas Series of daily closes, indexed by date

print(r.status, r.ratio, r.last_close_date, r.note)  # "pinned" | "not_pinned" | "insufficient"

frame = pinning_frame(closes)  # the daily series behind the flag: ratio, range, std ratio
```

`check` ignores closes dated on or after the given day. `insufficient` means fewer than 253
closes. Window lengths and threshold are parameters (`short`, `long`, `max_ratio`).

A runnable example with three synthetic stocks (normal, cash deal, stock deal):

```bash
python examples/synthetic.py
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

All tests run offline.

## Known limits

- The flag comes 9 to 14 trading days after an announcement (median 11 in the wider data).
- A deal that keeps the price pinned for more than about 126 trading days is no longer flagged:
  by then the quiet days dominate the one-year reference. Four fixes were tested against criteria
  set in advance; none passed ([DECISIONS.md](https://github.com/Elcando-GmbH/price-pinning/blob/main/docs/DECISIONS.md#long-deals)).
- Stock and cash-and-stock deals are not flagged while the price moves with the acquirer.
- Calibrated on two current cases in large caps; the wider check adds 34 historical cases.

## Author

Laura Kruse-Stecher, Elcando GmbH.

## License

MIT, Copyright (c) 2026 Elcando GmbH. For informational purposes only. Not investment advice.
