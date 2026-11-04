"""Three synthetic stocks: normal, cash takeover, stock deal. No data is downloaded.

    python examples/synthetic.py
"""

import datetime as dt

import numpy as np
import pandas as pd

from pricepinning import check, pinning_frame

rng = np.random.default_rng(7)


def series(returns):
    idx = pd.bdate_range("2025-01-02", periods=len(returns) + 1)
    return pd.Series(100 * np.cumprod(np.r_[1.0, 1.0 + np.asarray(returns)]), index=idx)


normal = rng.normal(0, 0.015, 300)
stocks = {
    "NORMAL": series(np.r_[normal, rng.normal(0, 0.015, 30)]),
    "CASH_DEAL": series(np.r_[normal, [0.30], rng.normal(0, 0.0015, 29)]),  # jump, then pinned to the offer
    "STOCK_DEAL": series(np.r_[normal, [0.15], rng.normal(0, 0.012, 29)]),  # moves with the acquirer
}

for name, closes in stocks.items():
    as_of = closes.index[-1].date() + dt.timedelta(days=1)
    r = check(name, closes, as_of)
    print(f"{name:10} {r.status:12} ratio {r.ratio:.2f}  range {r.range_short:.1%}")

frame = pinning_frame(stocks["CASH_DEAL"])
jump = 301  # position of the announcement day in the price series
first = int(np.argmax(frame["ratio"].to_numpy() <= 0.30))
print(f"\nCASH_DEAL first flagged {first - jump} trading days after the jump ({frame.index[first].date()})")
