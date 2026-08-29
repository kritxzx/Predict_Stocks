"""
Quant core: linear-regression trend channel, macro support/resistance
detection, price-structure classification and the composite signal
score used by both the dashboard (app.py) and the offline scanner
(main.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import argrelextrema

from config import (
    REGRESSION_WINDOW,
    CHANNEL_STD_MULT,
    SR_ORDER,
    SR_TOLERANCE_PCT,
    SR_LOOKBACK_DAYS,
)


def linear_regression_channel(
    close: pd.Series,
    window: int = REGRESSION_WINDOW,
    std_mult: float = CHANNEL_STD_MULT,
) -> dict:
    """
    Fit an OLS trend line through the most recent `window` closes and
    build a +-std_mult*sigma channel around it.

    Returns full-length series (aligned to `close`'s index, NaN
    outside the fitted window, ready to plot) plus scalar summary
    stats for the most recent bar:
        - r_squared, slope (price change per bar)
        - ev_target: where the trend line says price "should" be today
        - upper_band / lower_band: today's channel edges
    """
    window = min(window, len(close))
    y = close.iloc[-window:].to_numpy(dtype=float)
    x = np.arange(window, dtype=float)

    slope, intercept, r_value, _p_value, _std_err = stats.linregress(x, y)
    fitted = slope * x + intercept
    residuals = y - fitted
    std_dev = float(residuals.std(ddof=1)) if window > 2 else 0.0

    upper = fitted + std_mult * std_dev
    lower = fitted - std_mult * std_dev

    line_series = pd.Series(np.nan, index=close.index)
    upper_series = pd.Series(np.nan, index=close.index)
    lower_series = pd.Series(np.nan, index=close.index)
    line_series.iloc[-window:] = fitted
    upper_series.iloc[-window:] = upper
    lower_series.iloc[-window:] = lower

    return {
        "line": line_series,
        "upper": upper_series,
        "lower": lower_series,
        "r_squared": float(r_value ** 2),
        "slope": float(slope),
        "intercept": float(intercept),
        "std_dev": std_dev,
        "ev_target": float(fitted[-1]),
        "upper_band": float(upper[-1]),
        "lower_band": float(lower[-1]),
        "current_price": float(y[-1]),
        "window": window,
    }


def find_support_resistance(
    close: pd.Series,
    order: int = SR_ORDER,
    tolerance_pct: float = SR_TOLERANCE_PCT,
    lookback: int = SR_LOOKBACK_DAYS,
) -> list[float]:
    """
    Detect macro swing highs/lows over the last `lookback` bars and
    collapse levels that sit within `tolerance_pct` of each other into
    a single level (simple average). Returns a sorted list of price
    levels - a cheap way to get "S/R zones" with no external data.
    """
    series = close.iloc[-lookback:] if len(close) > lookback else close
    values = series.to_numpy(dtype=float)
    if len(values) < order * 2 + 1:
        return []

    hi_idx = argrelextrema(values, np.greater_equal, order=order)[0]
    lo_idx = argrelextrema(values, np.less_equal, order=order)[0]
    raw_levels = sorted(set(values[hi_idx].tolist() + values[lo_idx].tolist()))

    if not raw_levels:
        return []

    clustered: list[float] = []
    bucket = [raw_levels[0]]
    for level in raw_levels[1:]:
        if abs(level - bucket[-1]) / bucket[-1] <= tolerance_pct:
            bucket.append(level)
        else:
            clustered.append(sum(bucket) / len(bucket))
            bucket = [level]
    clustered.append(sum(bucket) / len(bucket))
    return clustered


def nearest_support_resistance(
    current_price: float, levels: list[float]
) -> tuple[float | None, float | None]:
    """Split detected levels into the nearest support (S1, below
    price) and nearest resistance (R1, above price)."""
    below = [lv for lv in levels if lv < current_price]
    above = [lv for lv in levels if lv > current_price]
    s1 = max(below) if below else None
    r1 = min(above) if above else None
    return s1, r1


def classify_structure(
    current_price: float,
    upper_band: float,
    lower_band: float,
    s1: float | None,
    r1: float | None,
    proximity_pct: float = 0.02,
) -> str:
    """Turn the channel + macro S/R levels into one of the labels
    defined in config.STRUCTURE_LABELS."""
    if current_price > upper_band:
        return "ABOVE_CHANNEL_EXTENDED"
    if current_price < lower_band:
        return "BELOW_CHANNEL_EXTENDED"
    if r1 is not None and abs(current_price - r1) / r1 <= proximity_pct:
        return "AT_R1_RESISTANCE"
    if s1 is not None:
        if current_price < s1:
            return "BELOW_S1_BREAKDOWN"
        if abs(current_price - s1) / s1 <= 0.05:
            return "ABOVE_S1_HOLDING"
    return "NEUTRAL"


def calculate_signal_score(model: dict) -> float:
    """
    Composite 0-100 screener score used to rank the universe in
    main.py. Rewards a well-fitted *up*trend (high R^2, positive
    slope) where price sits near the lower half of the channel (a
    pullback / better risk-reward entry) with room left to the EV
    target. Downtrends (slope <= 0) always score 0 - this screener
    only looks for long entries.
    """
    if model["slope"] <= 0:
        return 0.0

    r2_score = model["r_squared"] * 100

    band_range = model["upper_band"] - model["lower_band"]
    if band_range <= 0:
        proximity_score = 50.0
    else:
        pos_from_top = (model["upper_band"] - model["current_price"]) / band_range
        proximity_score = float(np.clip(pos_from_top * 100, 0, 100))

    upside_pct = (model["ev_target"] - model["current_price"]) / model["current_price"] * 100
    upside_score = float(np.clip(upside_pct * 5, 0, 100))

    score = r2_score * 0.40 + proximity_score * 0.35 + upside_score * 0.25
    return round(score, 1)


def refresh_with_live_price(model: dict, live_price: float) -> dict:
    """
    Swap a fresher "current price" (e.g. from a live quote poll) into
    an already-built model without re-fitting the regression - only
    the price-dependent fields (upside, structure, score) need
    recomputing, so this is essentially free to call often.
    """
    updated = dict(model)
    updated["current_price"] = live_price
    updated["upside_pct"] = round(
        (model["ev_target"] - live_price) / live_price * 100, 2
    )
    updated["structure"] = classify_structure(
        live_price, model["upper_band"], model["lower_band"], model["s1"], model["r1"]
    )
    updated["score"] = calculate_signal_score(updated)
    return updated


def forecast_price_path(model: dict, horizon_days: int = 20, confidence: float = 0.95) -> dict:
    """
    Extrapolate the fitted trend line `horizon_days` bars into the
    future using the standard OLS prediction-interval formula, so the
    uncertainty band widens the further out the projection goes -
    that's the honest way to show this: a statistical extrapolation of
    the recent trend, not a confident single-number prediction.
    """
    n = model["window"]
    slope = model["slope"]
    intercept = model["intercept"]
    s = model["std_dev"]

    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    sxx = float(np.sum((x - x_mean) ** 2)) if n > 1 else 1.0

    future_x = np.arange(n, n + horizon_days, dtype=float)
    point = slope * future_x + intercept

    dof = max(n - 2, 1)
    t_mult = float(stats.t.ppf(0.5 + confidence / 2, dof))
    se = s * np.sqrt(1 + 1 / n + (future_x - x_mean) ** 2 / sxx) if sxx > 0 else np.full_like(future_x, s)
    margin = t_mult * se

    return {
        "horizon_days": horizon_days,
        "confidence": confidence,
        "target_price": float(point[-1]),
        "target_low": float(point[-1] - margin[-1]),
        "target_high": float(point[-1] + margin[-1]),
        "path": point,
        "path_low": point - margin,
        "path_high": point + margin,
    }


def suggest_entry_setup(model: dict, forecast: dict) -> dict:
    """
    Turn the model + forecast into a concrete entry/stop/target setup:
    an entry zone anchored on macro support (falling back to the
    statistical lower channel band), a stop sized off the same
    residual volatility used for the channel, and the forecast target
    for the reward side - then the resulting risk:reward ratio.
    """
    current = model["current_price"]
    lower_band = model["lower_band"]
    s1 = model["s1"]
    sd = model["std_dev"] or (current * 0.01)  # tiny fallback so bands never collapse to zero

    if model["slope"] <= 0:
        # This screener only looks for long entries inside an uptrend -
        # a "buy zone" on a downtrending name would be misleading, so
        # flag it instead of returning a number that looks actionable.
        return {
            "entry_low": None,
            "entry_high": None,
            "stop_loss": None,
            "target": float(forecast["target_price"]),
            "risk_reward": None,
            "entry_status": "DOWNTREND_NO_SETUP",
        }

    # Prefer macro support S1 when it's a realistic, nearby level;
    # otherwise fall back to the statistical lower band as the "cheap" zone.
    if s1 is not None and lower_band * 0.9 <= s1 <= current:
        entry_ref = s1
    else:
        entry_ref = lower_band

    buffer = sd * 0.25
    entry_low = entry_ref - buffer
    entry_high = entry_ref + buffer
    stop_loss = entry_low - sd * 1.0  # one more sigma of cushion below the zone

    target = forecast["target_price"]
    reward = target - entry_high
    risk = entry_high - stop_loss
    risk_reward = round(reward / risk, 2) if risk > 0 else None

    if current < stop_loss:
        entry_status = "BELOW_ZONE_RISK"
    elif current <= entry_high:
        entry_status = "IN_ZONE"
    else:
        entry_status = "WAIT_FOR_PULLBACK"

    return {
        "entry_low": float(entry_low),
        "entry_high": float(entry_high),
        "stop_loss": float(stop_loss),
        "target": float(target),
        "risk_reward": risk_reward,
        "entry_status": entry_status,
    }


def add_forecast(model: dict, horizon_days: int = 20, confidence: float = 0.95) -> dict:
    """One-stop call: attach a forward price forecast and an
    entry/stop/target setup onto an already-built model dict."""
    forecast = forecast_price_path(model, horizon_days=horizon_days, confidence=confidence)
    entry_setup = suggest_entry_setup(model, forecast)
    return {**model, "forecast": forecast, "entry_setup": entry_setup}


def build_model(close: pd.Series) -> dict:
    """
    One-stop call used by both app.py and main.py: fits the channel,
    detects S/R, classifies structure and scores the setup for a
    single ticker's close-price series.
    """
    channel = linear_regression_channel(close)
    levels = find_support_resistance(close)
    s1, r1 = nearest_support_resistance(channel["current_price"], levels)
    structure = classify_structure(
        channel["current_price"], channel["upper_band"], channel["lower_band"], s1, r1
    )
    score = calculate_signal_score(channel)

    return {
        **channel,
        "s1": s1,
        "r1": r1,
        "structure": structure,
        "score": score,
        "upside_pct": round(
            (channel["ev_target"] - channel["current_price"]) / channel["current_price"] * 100, 2
        ),
    }
