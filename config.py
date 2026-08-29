"""
Central configuration for the US Quant Screener.
All tunable parameters, file paths and secrets live here so the rest
of the codebase never hard-codes a magic number or a path string.
"""
import os
from pathlib import Path

# Optional: read a local .env file when running outside Streamlit Cloud
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_secret(key: str, default=None):
    """Look for a secret first in Streamlit's secrets store (used on
    Streamlit Community Cloud), then fall back to an environment
    variable (used by the GitHub Actions cron job / local runs)."""
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

FAVORITES_PATH = OUTPUT_DIR / "favorites.json"
SIGNALS_PATH = OUTPUT_DIR / "signals.csv"

# ----------------------------------------------------------------------
# Secrets
# ----------------------------------------------------------------------
DISCORD_WEBHOOK_URL = _get_secret("DISCORD_WEBHOOK_URL", "")

# ----------------------------------------------------------------------
# Data settings
# ----------------------------------------------------------------------
CHART_PERIOD = "2y"          # how much history to pull / display
CHART_INTERVAL = "1d"
REQUEST_TIMEOUT = 15

# ----------------------------------------------------------------------
# Model settings
# ----------------------------------------------------------------------
REGRESSION_WINDOW = 90       # trading days used to fit the trend channel
CHANNEL_STD_MULT = 2.0       # +/- sigma multiplier for the channel bounds
SR_ORDER = 10                # bar spacing used to detect swing highs/lows
SR_TOLERANCE_PCT = 0.02      # cluster S/R levels within +-2%
SR_LOOKBACK_DAYS = 504       # ~2y of daily bars used for macro S/R

# ----------------------------------------------------------------------
# Screener settings
# ----------------------------------------------------------------------
MIN_SIGNAL_SCORE = 55.0      # minimum score to be listed as an actionable signal
TOP_N_ALERTS = 10            # how many rows to push to Discord per run

# ----------------------------------------------------------------------
# Forecast settings
# ----------------------------------------------------------------------
DEFAULT_FORECAST_HORIZON = 20   # trading days (~1 month) used for main.py's scan output
FORECAST_CONFIDENCE = 0.95      # width of the projected price range
FORECAST_HORIZONS = {
    5: "1 สัปดาห์",
    10: "2 สัปดาห์",
    20: "1 เดือน",
    60: "3 เดือน",
}

DEFAULT_UNIVERSE = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "ORCL", "CRM",
    # Semis / hardware
    "AMD", "QCOM", "TXN", "MU", "INTC", "ASML", "LRCX", "AMAT", "KLAC",
    # Financials
    "JPM", "BAC", "GS", "MS", "V", "MA", "AXP", "SCHW",
    # Healthcare
    "LLY", "UNH", "JNJ", "PFE", "MRK", "ABBV", "TMO",
    # Consumer
    "COST", "WMT", "HD", "NKE", "SBUX", "MCD", "PG", "KO", "PEP",
    # Industrials / energy
    "CAT", "BA", "GE", "XOM", "CVX", "LIN",
    # Growth / momentum names often screened
    "OKLO", "VST", "SAP", "PLTR", "SMCI", "CRWD", "NET", "SNOW", "SHOP",
]

# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------
PAGE_TITLE = "US Quant Screener — Dashboard Terminal"
PAGE_ICON = "🖥️"

COLORS = {
    "bg": "#0e1117",
    "candle_up": "#26a69a",
    "candle_down": "#ef5350",
    "ev_line": "#22d3ee",
    "upper_band": "#ef5350",
    "lower_band": "#26a69a",
    "support": "#facc15",
    "resistance": "#f472b6",
    "forecast": "#a78bfa",
    "buy_zone": "#4ade80",
    "stop": "#f87171",
}

STRUCTURE_LABELS = {
    "ABOVE_CHANNEL_EXTENDED": ("🔥 เหนือกรอบ (Overbought)", "#f97316"),
    "ABOVE_S1_HOLDING": ("🟢 ยืนเหนือแนวรับ (Holding Support)", "#22c55e"),
    "AT_R1_RESISTANCE": ("🟡 ทดสอบแนวต้าน (At Resistance)", "#eab308"),
    "BELOW_S1_BREAKDOWN": ("🔴 หลุดแนวรับ (Breakdown)", "#ef4444"),
    "BELOW_CHANNEL_EXTENDED": ("🧊 ต่ำกว่ากรอบ (Oversold)", "#38bdf8"),
    "NEUTRAL": ("⚪ ปกติ (Neutral)", "#94a3b8"),
}

ENTRY_STATUS_LABELS = {
    "IN_ZONE": ("🟢 ราคาอยู่ในโซนเข้าซื้อแล้ว", "#22c55e"),
    "WAIT_FOR_PULLBACK": ("🟡 ยังไม่ถึงโซน — รอราคาย่อตัวก่อน", "#eab308"),
    "BELOW_ZONE_RISK": ("🔴 ราคาหลุดต่ำกว่าโซนที่ประเมินไว้แล้ว", "#ef4444"),
    "DOWNTREND_NO_SETUP": ("⚫ เทรนด์เป็นขาลง — ไม่มีจุดเข้าซื้อ", "#64748b"),
}

