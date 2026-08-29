"""
Thin Discord notifier. Uses a plain incoming webhook (no bot token /
gateway connection needed), which is the right tool for a scheduled
GitHub Actions job that just needs to fire-and-forget a message -
no persistent bot process required.
"""
from __future__ import annotations

import logging

import requests

from config import DISCORD_WEBHOOK_URL, STRUCTURE_LABELS

logger = logging.getLogger(__name__)


def _post(payload: dict, webhook_url: str | None = None) -> bool:
    url = webhook_url or DISCORD_WEBHOOK_URL
    if not url:
        logger.info("No Discord webhook configured - skipping notification.")
        return False
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Discord webhook failed: %s", exc)
        return False


def _signal_embed(ticker: str, model: dict) -> dict:
    label, color_hex = STRUCTURE_LABELS.get(model["structure"], ("UNKNOWN", "#94a3b8"))
    color_int = int(color_hex.lstrip("#"), 16)
    fields = [
        {"name": "ราคาปัจจุบัน", "value": f"${model['current_price']:.2f}", "inline": True},
        {"name": "R²", "value": f"{model['r_squared']*100:.1f}%", "inline": True},
        {"name": "EV Target", "value": f"${model['ev_target']:.2f} ({model['upside_pct']:+.1f}%)", "inline": True},
        {"name": "โครงสร้าง", "value": label, "inline": False},
    ]
    # forecast/entry fields are optional - only present when the caller
    # ran the model through mathematical_models.add_forecast()
    if model.get("forecast_target") is not None:
        days = model.get("forecast_days", "?")
        fields.append({"name": f"เป้าหมาย ({days}d)", "value": f"${model['forecast_target']:.2f}", "inline": True})
    if model.get("entry_low") is not None:
        fields.append({
            "name": "โซนเข้าซื้อ / Stop",
            "value": f"${model['entry_low']:.2f}–${model['entry_high']:.2f} / ${model['stop_loss']:.2f}",
            "inline": True,
        })
    if model.get("risk_reward") is not None:
        fields.append({"name": "Risk:Reward", "value": f"1:{model['risk_reward']}", "inline": True})

    return {
        "title": f"{ticker} — Signal Score {model['score']}/100",
        "color": color_int,
        "fields": fields,
    }


def send_signal_alert(ticker: str, model: dict, webhook_url: str | None = None) -> bool:
    """Push a single-ticker signal card to Discord."""
    payload = {"embeds": [_signal_embed(ticker, model)]}
    return _post(payload, webhook_url)


def send_daily_summary(
    results: list[tuple[str, dict]],
    webhook_url: str | None = None,
    top_n: int = 10,
) -> bool:
    """
    Push the top N scanned tickers (already sorted by score, best
    first) as one message with multiple embeds - keeps a full scan to
    a single Discord notification instead of spamming one per name.
    """
    if not results:
        return False
    embeds = [_signal_embed(tkr, model) for tkr, model in results[:top_n]]
    payload = {
        "content": f"📊 **US Quant Screener** — {len(results)} setups found, showing top {min(top_n, len(results))}",
        "embeds": embeds[:10],  # Discord hard limit: 10 embeds per message
    }
    return _post(payload, webhook_url)
