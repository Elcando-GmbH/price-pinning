import datetime as dt

import numpy as np
import pandas as pd
import pytest

from pricepinning import MAX_RATIO, check, is_pinned, pinning_frame


def _series(returns, start=100.0):
    idx = pd.bdate_range("2024-01-02", periods=len(returns) + 1)
    prices = start * np.cumprod(np.r_[1.0, 1.0 + np.asarray(returns)])
    return pd.Series(prices, index=idx)


def _normal(n, sd=0.015, seed=1):
    return np.random.default_rng(seed).normal(0.0, sd, n)


def test_normal_stock_ratio_near_one():
    f = pinning_frame(_series(_normal(600)))
    last = f["ratio"].iloc[-1]
    assert 0.5 < last < 1.6


def test_cash_deal_pinned_after_jump():
    r = np.r_[_normal(400), [0.30], _normal(30, sd=0.0015, seed=2)]
    f = pinning_frame(_series(r))
    # right after the jump the robust ratio is still normal, the std ratio explodes
    day_after = f.iloc[402]
    assert day_after["ratio"] > 0.5
    assert day_after["std_ratio"] > 2
    # after 20 quiet days the jump has left the short window: clearly pinned
    last = f.iloc[-1]
    assert last["ratio"] < 0.2
    assert last["range_short"] < 0.03
    assert is_pinned(last, max_ratio=0.3, max_range=0.03)


def test_median_reacts_before_window_is_clean():
    # a single jump inside the window does not hold the median up
    r = np.r_[_normal(400), [0.30], _normal(15, sd=0.0015, seed=3)]
    f = pinning_frame(_series(r))
    assert f["ratio"].iloc[-1] < 0.4
    assert f["std_ratio"].iloc[-1] > 1


def test_no_value_without_full_year():
    f = pinning_frame(_series(_normal(200)))
    assert f["ratio"].isna().all()
    assert not is_pinned(f.iloc[-1], max_ratio=10)


def test_point_in_time():
    r = np.r_[_normal(400), _normal(40, sd=0.001, seed=4)]
    full = pinning_frame(_series(r))
    cut = pinning_frame(_series(r[:420]))
    pd.testing.assert_series_equal(full["ratio"].iloc[:421], cut["ratio"], check_names=False)


def test_bad_windows_rejected():
    with pytest.raises(ValueError):
        pinning_frame(_series(_normal(300)), short=20, long=20)


def test_check_uses_closes_before_as_of_only():
    r = np.r_[_normal(400), [0.30], _normal(30, sd=0.0015, seed=2)]
    s = _series(r)
    day = s.index[-1].date()
    res = check("T", s, day + dt.timedelta(days=1))
    assert res.status == "pinned" and res.last_close_date == day and res.ratio <= MAX_RATIO
    # evaluated for the last day itself, it must not see that day's close
    assert check("T", s, day).last_close_date == s.index[-2].date()


def test_flag_clears_when_volatility_returns():
    r = np.r_[_normal(400), [0.30], _normal(30, sd=0.0015, seed=2), _normal(25, sd=0.02, seed=5)]
    s = _series(r)
    assert check("T", s, s.index[-1].date() + dt.timedelta(days=1)).status == "not_pinned"


def test_check_insufficient_and_stale():
    s = _series(_normal(100))
    assert check("T", s, s.index[-1].date() + dt.timedelta(days=1)).status == "insufficient"
    assert check("T", s, s.index[0].date()).note == "no close before as_of"
    long_s = _series(_normal(400))
    res = check("T", long_s, long_s.index[-1].date() + dt.timedelta(days=10))
    assert res.status == "not_pinned" and "days old" in res.note


def test_stock_deal_not_pinned():
    # price keeps moving with the acquirer's share: no flag
    r = np.r_[_normal(400), [0.15], _normal(40, sd=0.012, seed=6)]
    s = _series(r)
    assert check("T", s, s.index[-1].date() + dt.timedelta(days=1)).status == "not_pinned"


def test_custom_threshold():
    r = np.r_[_normal(400), [0.30], _normal(30, sd=0.0015, seed=2)]
    s = _series(r)
    day = s.index[-1].date() + dt.timedelta(days=1)
    assert check("T", s, day, max_ratio=0.01).status == "not_pinned"
