"""Price pinning: a price that has stopped moving relative to its own history.

Typical cause: a pending cash takeover offer. The price sticks to the offer and its daily moves
shrink to a fraction of their usual size. The measure looks only at the price series. It needs
no event data and no judgement, and it uses only data up to the day it is evaluated for.

For every day t:

    ratio_t = median(|r|, last ``short`` returns) / median(|r|, last ``long`` returns)

with simple daily returns r. Medians instead of standard deviations: a single announcement jump
inflates a standard deviation for weeks, a median not. A ratio well below 1 means the stock
moves much less than it normally does. ``range_short`` (max/min - 1 of the closes in the short
window) is reported as a second, easily checked description of the same state.

A stock is flagged as pinned on a day if ``ratio`` on the last close before that day is at or
below ``MAX_RATIO``. The flag clears as soon as the ratio is above the threshold again. Window
lengths and threshold were calibrated in November 2026 (docs/DECISIONS.md, D2).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

DEFAULT_SHORT = 20
DEFAULT_LONG = 252
MAX_RATIO = 0.30
STALE_DAYS = 5


def pinning_frame(closes: pd.Series, short: int = DEFAULT_SHORT, long: int = DEFAULT_LONG) -> pd.DataFrame:
    """Per-day pinning measures for one price series (index: dates, ascending).

    Columns: ``ret``, ``med_short``, ``med_long``, ``ratio``, ``range_short``, ``std_ratio``.
    Values are NaN until ``long`` returns (``long + 1`` prices) are available.
    """
    if short < 2 or long <= short:
        raise ValueError("need 2 <= short < long")
    s = pd.Series(closes, dtype="float64").dropna()
    s = s[s > 0].sort_index()
    ret = s.pct_change()
    a = ret.abs()
    out = pd.DataFrame(index=s.index)
    out["ret"] = ret
    out["med_short"] = a.rolling(short, min_periods=short).median()
    out["med_long"] = a.rolling(long, min_periods=long).median()
    out["ratio"] = out["med_short"] / out["med_long"]
    out.loc[out["med_long"] <= 0, "ratio"] = float("nan")
    window = short + 1
    out["range_short"] = s.rolling(window, min_periods=window).max() / s.rolling(window, min_periods=window).min() - 1
    out["std_ratio"] = ret.rolling(short, min_periods=short).std() / ret.rolling(long, min_periods=long).std()
    out.loc[out["med_long"].isna(), ["ratio", "range_short", "std_ratio"]] = float("nan")
    return out


def is_pinned(frame_row: pd.Series, max_ratio: float = MAX_RATIO, max_range: float | None = None) -> bool:
    """Flag for one day. ``max_range`` is optional. NaN (too little history) is never pinned."""
    ratio = frame_row.get("ratio")
    if ratio is None or pd.isna(ratio) or ratio > max_ratio:
        return False
    if max_range is not None:
        rng = frame_row.get("range_short")
        if rng is None or pd.isna(rng) or rng > max_range:
            return False
    return True


@dataclass(frozen=True)
class PinningResult:
    ticker: str
    as_of: dt.date
    status: str  # "pinned" | "not_pinned" | "insufficient"
    last_close_date: dt.date | None
    ratio: float | None
    range_short: float | None
    note: str = ""


def check(
    ticker: str,
    closes: pd.Series,
    as_of: dt.date,
    *,
    short: int = DEFAULT_SHORT,
    long: int = DEFAULT_LONG,
    max_ratio: float = MAX_RATIO,
) -> PinningResult:
    """Evaluate one stock for the day ``as_of``.

    Uses only closes dated strictly before ``as_of``, so the result is the same whether it is
    computed on that morning or years later from a stored history. ``insufficient`` means fewer
    than ``long + 1`` closes; what to do with such a stock is up to the caller.
    """
    s = pd.Series(closes, dtype="float64")
    s.index = pd.DatetimeIndex(s.index).normalize()
    s = s[s.index < pd.Timestamp(as_of)]
    if s.empty:
        return PinningResult(ticker, as_of, "insufficient", None, None, None, "no close before as_of")
    frame = pinning_frame(s, short, long)
    last = frame.iloc[-1]
    last_date = frame.index[-1].date()
    note = ""
    if (as_of - last_date).days > STALE_DAYS:
        note = f"last close {last_date} is more than {STALE_DAYS} days old"
    ratio = None if pd.isna(last["ratio"]) else float(last["ratio"])
    rng = None if pd.isna(last["range_short"]) else float(last["range_short"])
    if ratio is None:
        return PinningResult(ticker, as_of, "insufficient", last_date, None, rng, note or f"fewer than {long + 1} closes")
    status = "pinned" if is_pinned(last, max_ratio) else "not_pinned"
    return PinningResult(ticker, as_of, status, last_date, ratio, rng, note)
