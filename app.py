"""
Streamlit dashboard - the "US Quant Screener" terminal.

Two modes, picked from the sidebar:
  - Deep-Dive รายหุ้น        : full trend-channel breakdown for one ticker
  - ผลการสแกนทั้งตลาด        : browse the latest offline scan
                               (outputs/signals.csv, produced by main.py)
"""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from data_processing import get_price_history, get_live_price
from mathematical_models import build_model, refresh_with_live_price, add_forecast

st.set_page_config(page_title=config.PAGE_TITLE, page_icon=config.PAGE_ICON, layout="wide")


# ----------------------------------------------------------------------
# Favorites persistence (outputs/favorites.json)
# ----------------------------------------------------------------------
def load_favorites() -> list[str]:
    if config.FAVORITES_PATH.exists():
        try:
            return json.loads(config.FAVORITES_PATH.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_favorites(favorites: list[str]) -> None:
    config.FAVORITES_PATH.write_text(json.dumps(favorites, indent=2, ensure_ascii=False))


if "favorites" not in st.session_state:
    st.session_state.favorites = load_favorites()
if "ticker" not in st.session_state:
    st.session_state.ticker = st.session_state.favorites[0] if st.session_state.favorites else "AAPL"


# ----------------------------------------------------------------------
# Cached fetchers (UI-layer caching lives here, not in data_processing.py,
# so that module stays framework-agnostic and reusable by main.py)
# ----------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)  # 5 min - this pulls 2y of OHLCV, no need to refresh every second
def cached_history(ticker: str) -> pd.DataFrame | None:
    return get_price_history(ticker)


@st.cache_data(ttl=20, show_spinner=False)  # 20s - cheap quote call, safe to poll often
def cached_live_price(ticker: str) -> dict | None:
    return get_live_price(ticker)


@st.cache_data(ttl=900, show_spinner=False)
def cached_scan() -> pd.DataFrame | None:
    if config.SIGNALS_PATH.exists():
        df = pd.read_csv(config.SIGNALS_PATH)
        return df if not df.empty else None
    return None


# ----------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🧩 Control Panel")
    st.caption("โหมดการทำงาน")
    mode = st.radio(
        "โหมดการทำงาน",
        ["Deep-Dive รายหุ้น", "ผลการสแกนทั้งตลาด"],
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("### 🔍 ค้นหาหุ้น")
    st.caption("ใส่ชื่อหุ้น US (เช่น AAPL, TSLA, NVDA)")
    typed = st.text_input(
        "ticker_input", value=st.session_state.ticker, label_visibility="collapsed"
    ).strip().upper()
    if typed:
        st.session_state.ticker = typed

    is_fav = st.session_state.ticker in st.session_state.favorites
    fav_label = "❌ ลบออกจากหุ้นโปรด" if is_fav else "⭐ เพิ่มเป็นหุ้นโปรด"
    if st.button(fav_label, width="stretch"):
        if is_fav:
            st.session_state.favorites.remove(st.session_state.ticker)
        else:
            st.session_state.favorites.append(st.session_state.ticker)
        save_favorites(st.session_state.favorites)
        st.rerun()

    st.divider()
    st.markdown("### ⭐ หุ้นโปรดของคุณ (Shortcuts)")
    if not st.session_state.favorites:
        st.caption("ยังไม่มีหุ้นโปรด")
    for fav in st.session_state.favorites:
        if st.button(f"✅ {fav}", key=f"fav_{fav}", width="stretch"):
            st.session_state.ticker = fav
            st.rerun()


# ----------------------------------------------------------------------
# Chart builder
# ----------------------------------------------------------------------
def build_chart(df: pd.DataFrame, model: dict, ticker: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            increasing_line_color=config.COLORS["candle_up"],
            decreasing_line_color=config.COLORS["candle_down"],
            name="Price",
        )
    )
    fig.add_trace(go.Scatter(
        x=df.index, y=model["line"], mode="lines",
        line=dict(color=config.COLORS["ev_line"], width=2),
        name="Expected Value",
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=model["upper"], mode="lines",
        line=dict(color=config.COLORS["upper_band"], width=1, dash="dot"),
        name="+2σ Channel",
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=model["lower"], mode="lines",
        line=dict(color=config.COLORS["lower_band"], width=1, dash="dot"),
        name="-2σ Channel",
    ))

    if model["s1"]:
        fig.add_hline(
            y=model["s1"], line_dash="dash", line_color=config.COLORS["support"],
            annotation_text="S1", annotation_position="right",
        )
    if model["r1"]:
        fig.add_hline(
            y=model["r1"], line_dash="dash", line_color=config.COLORS["resistance"],
            annotation_text="R1", annotation_position="right",
        )

    forecast = model.get("forecast")
    setup = model.get("entry_setup")

    if forecast:
        future_dates = pd.bdate_range(start=df.index[-1], periods=forecast["horizon_days"] + 1)[1:]
        fig.add_trace(go.Scatter(
            x=future_dates, y=forecast["path_high"], mode="lines",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=future_dates, y=forecast["path_low"], mode="lines",
            line=dict(width=0), fill="tonexty", fillcolor="rgba(167,139,250,0.18)",
            name=f"Forecast {int(forecast['confidence']*100)}% range", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=future_dates, y=forecast["path"], mode="lines",
            line=dict(color=config.COLORS["forecast"], width=2, dash="dashdot"),
            name="Forecast",
        ))

    if setup and setup.get("entry_low") is not None:
        fig.add_hline(
            y=setup["entry_high"], line_dash="dot", line_color=config.COLORS["buy_zone"],
            annotation_text="Buy Zone", annotation_position="left",
        )
        fig.add_hline(y=setup["entry_low"], line_dash="dot", line_color=config.COLORS["buy_zone"])
        fig.add_hline(
            y=setup["stop_loss"], line_dash="dot", line_color=config.COLORS["stop"],
            annotation_text="Stop", annotation_position="left",
        )

    fig.update_layout(
        title=f"📈 Linear Regression Channel & Macro S/R: {ticker}",
        template="plotly_dark",
        paper_bgcolor=config.COLORS["bg"],
        plot_bgcolor=config.COLORS["bg"],
        xaxis_rangeslider_visible=False,
        height=560,
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01),
        margin=dict(l=10, r=10, t=60, b=10),
    )
    return fig


# ----------------------------------------------------------------------
# Deep-Dive view
# ----------------------------------------------------------------------
def render_deep_dive():
    ticker = st.session_state.ticker
    if not ticker:
        st.info("พิมพ์ชื่อหุ้นทางด้านซ้ายเพื่อเริ่มต้น")
        return

    with st.spinner(f"กำลังโหลดข้อมูล {ticker}..."):
        df = cached_history(ticker)

    if df is None or df.empty or len(df) < 30:
        st.error(f"ไม่พบข้อมูลราคาของ '{ticker}' — ลองตรวจสอบชื่อย่อหุ้นอีกครั้ง")
        return

    model = build_model(df["Close"])

    # Overlay a near-real-time quote on top of the daily-bar model so the
    # headline price/structure reflect the latest tick, not just the last
    # cached daily close. Cheap call (fast_info), safe to poll often.
    live = cached_live_price(ticker)
    if live and live["last_price"]:
        model = refresh_with_live_price(model, live["last_price"])

    label, color = config.STRUCTURE_LABELS.get(model["structure"], ("UNKNOWN", "#94a3b8"))

    top_l, top_r = st.columns([5, 1])
    top_l.markdown(f"# 🖥️ {config.PAGE_TITLE}")
    with top_r:
        st.write("")  # vertical spacer to align button with title
        if st.button("🔄 รีเฟรชราคา", width="stretch"):
            cached_history.clear()
            cached_live_price.clear()
            st.rerun()
    if live:
        st.caption(f"ราคาล่าสุด (real-time quote) ณ ตอนนี้ — เปลี่ยนแปลง {live['change_pct']:+.2f}% จากปิดวันก่อน" if live["change_pct"] is not None else "ราคาล่าสุด (real-time quote)")
    else:
        st.caption("ไม่สามารถดึงราคาล่าสุดได้ — แสดงราคาปิดล่าสุดจากข้อมูลรายวันแทน")

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.3])
    c1.metric("ราคาปัจจุบัน", f"${model['current_price']:.2f}")
    c2.metric("ค่าสถิติ R²", f"{model['r_squared']*100:.1f}%")
    c3.metric("ราคาเหมาะสม (EV Target)", f"${model['ev_target']:.2f}", f"{model['upside_pct']:+.1f}%")
    with c4:
        st.markdown("สถานะทางโครงสร้างราคา:")
        st.markdown(
            f"<span style='background:{color}22;color:{color};padding:4px 10px;"
            f"border-radius:6px;font-weight:600'>{label}</span>",
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------------
    # Forecast + entry/stop/target setup
    # --------------------------------------------------------------
    st.divider()
    st.markdown("### 🎯 พยากรณ์ราคา & จุดเข้าซื้อ")
    horizon_days = st.select_slider(
        "ระยะเวลาพยากรณ์",
        options=list(config.FORECAST_HORIZONS.keys()),
        value=config.DEFAULT_FORECAST_HORIZON,
        format_func=lambda d: config.FORECAST_HORIZONS[d],
    )
    model = add_forecast(model, horizon_days=horizon_days, confidence=config.FORECAST_CONFIDENCE)
    fc, setup = model["forecast"], model["entry_setup"]

    f1, f2, f3, f4 = st.columns(4)
    target_chg = (fc["target_price"] - model["current_price"]) / model["current_price"] * 100
    f1.metric(f"เป้าหมายราคา ({config.FORECAST_HORIZONS[horizon_days]})", f"${fc['target_price']:.2f}", f"{target_chg:+.1f}%")
    f2.metric(f"ช่วงความเชื่อมั่น {int(fc['confidence']*100)}%", f"${fc['target_low']:.2f} – ${fc['target_high']:.2f}")
    if setup["entry_low"] is not None:
        f3.metric("โซนแนะนำเข้าซื้อ", f"${setup['entry_low']:.2f} – ${setup['entry_high']:.2f}")
        f4.metric("จุดตัดขาดทุน (Stop)", f"${setup['stop_loss']:.2f}")
    else:
        f3.metric("โซนแนะนำเข้าซื้อ", "—")
        f4.metric("จุดตัดขาดทุน (Stop)", "—")

    s_label, s_color = config.ENTRY_STATUS_LABELS.get(setup["entry_status"], ("UNKNOWN", "#94a3b8"))
    rr_text = f" · Risk:Reward ≈ 1:{setup['risk_reward']}" if setup["risk_reward"] is not None else ""
    st.markdown(
        f"<span style='background:{s_color}22;color:{s_color};padding:4px 10px;"
        f"border-radius:6px;font-weight:600'>{s_label}</span>{rr_text}",
        unsafe_allow_html=True,
    )
    st.caption(
        "⚠️ ตัวเลขทั้งหมดคำนวณจากการยืดเส้นแนวโน้มในอดีตไปข้างหน้าทางสถิติเท่านั้น "
        "ไม่ใช่การรับประกันว่าราคาจะไปถึง — ใช้ประกอบการตัดสินใจ ไม่ใช่คำแนะนำการลงทุน"
    )

    st.plotly_chart(build_chart(df, model, ticker), width="stretch")

    with st.expander("รายละเอียดโมเดล (Model detail)"):
        d1, d2, d3 = st.columns(3)
        d1.write(f"**Slope (ต่อวัน):** {model['slope']:.4f}")
        d1.write(f"**หน้าต่างถดถอย (bars):** {model['window']}")
        d2.write(f"**Support (S1):** {'$' + format(model['s1'], '.2f') if model['s1'] else '—'}")
        d2.write(f"**Resistance (R1):** {'$' + format(model['r1'], '.2f') if model['r1'] else '—'}")
        d3.write(f"**Signal Score:** {model['score']}/100")
        d3.write(f"**Std dev of residuals:** {model['std_dev']:.2f}")


# ----------------------------------------------------------------------
# Market-wide scan view
# ----------------------------------------------------------------------
def render_scan():
    st.markdown(f"# 🖥️ {config.PAGE_TITLE}")
    st.caption("ผลการสแกนทั้งตลาด — สร้างโดย main.py (แนะนำให้รันผ่าน GitHub Actions ตามตารางเวลา)")

    scan = cached_scan()
    if scan is None or scan.empty:
        st.warning(
            "ยังไม่มีผลสแกน — รันคำสั่ง `python main.py` เพื่อสร้างไฟล์ outputs/signals.csv ก่อน"
        )
        return

    scanned_at = scan["scanned_at"].max() if "scanned_at" in scan else "—"
    st.caption(f"อัปเดตล่าสุด: {scanned_at}")

    min_score = st.slider("กรองด้วย Signal Score ขั้นต่ำ", 0, 100, int(config.MIN_SIGNAL_SCORE))
    filtered = scan[scan["score"] >= min_score].sort_values("score", ascending=False)

    st.dataframe(
        filtered.rename(columns={
            "ticker": "Ticker", "price": "Price", "r_squared": "R² (%)",
            "ev_target": "EV Target", "upside_pct": "Upside (%)",
            "structure": "Structure", "score": "Score", "s1": "S1", "r1": "R1",
            "forecast_target": "Forecast Target", "forecast_low": "Forecast Low",
            "forecast_high": "Forecast High", "entry_low": "Entry Low",
            "entry_high": "Entry High", "stop_loss": "Stop", "risk_reward": "R:R",
            "entry_status": "Entry Status",
        }),
        width="stretch",
        hide_index=True,
    )

    picked = st.selectbox("เปิดดู Deep-Dive ของ:", ["—"] + filtered["ticker"].tolist())
    if picked != "—":
        st.session_state.ticker = picked
        st.rerun()


# ----------------------------------------------------------------------
if mode == "Deep-Dive รายหุ้น":
    render_deep_dive()
else:
    render_scan()

st.caption("⚠️ เครื่องมือนี้ใช้เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน")
