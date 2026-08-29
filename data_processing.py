"""
Data access layer. Pure functions only - no Streamlit / Discord
imports here so this module can be reused by both app.py (wrapped
with st.cache_data) and main.py (plain calls from a cron job).
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from config import CHART_PERIOD, CHART_INTERVAL

logger = logging.getLogger(__name__)


def get_price_history(
    ticker: str,
    period: str = CHART_PERIOD,
    interval: str = CHART_INTERVAL,
    retries: int = 2,
) -> pd.DataFrame | None:
    """
    Fetch OHLCV history for one ticker. Returns None (never raises) on
    failure so callers can skip bad tickers without crashing a scan.
    """
    ticker = ticker.strip().upper()
    last_err = None
    for attempt in range(retries + 1):
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
            if df is None or df.empty:
                raise ValueError(f"no data returned for {ticker}")
            df = df.rename(columns=str.title)
            df.index.name = "Date"
            return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        except Exception as exc:  # noqa: BLE001 - want to catch & retry any provider hiccup
            last_err = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    logger.warning("Failed to fetch %s: %s", ticker, last_err)
    return None


def get_universe_history(
    tickers: list[str],
    period: str = CHART_PERIOD,
    interval: str = CHART_INTERVAL,
    pause: float = 0.3,
) -> dict[str, pd.DataFrame]:
    """
    Sequentially fetch history for a list of tickers with a small
    pause between requests (kinder to the free data endpoint than one
    giant batch call, and easier to attribute failures to a specific
    symbol).
    """
    out: dict[str, pd.DataFrame] = {}
    for i, tkr in enumerate(tickers):
        df = get_price_history(tkr, period=period, interval=interval)
        if df is not None and len(df) > 30:
            out[tkr] = df
        if pause and i < len(tickers) - 1:
            time.sleep(pause)
    return out


def get_live_price(ticker: str) -> dict | None:
    """
    Lightweight current-quote fetch - uses yfinance's fast_info instead
    of history(), so it's cheap enough to poll every 20-30s for a
    near-real-time headline price without re-downloading 2y of OHLCV
    just to refresh one number.
    """
    ticker = ticker.strip().upper()
    try:
        fi = yf.Ticker(ticker).fast_info
        last = fi.last_price
        prev_close = fi.previous_close
        if last is None:
            return None
        return {
            "last_price": float(last),
            "previous_close": float(prev_close) if prev_close else None,
            "change_pct": round((last - prev_close) / prev_close * 100, 2) if prev_close else None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch live price for %s: %s", ticker, exc)
        return None


def validate_ticker(ticker: str) -> bool:
    """Cheap existence check the search box can use before doing a full fetch."""
    return get_price_history(ticker, period="5d", retries=0) is not None
