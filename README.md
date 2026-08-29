# US Quant Screener

Dashboard + offline scanner for spotting US-stock pullback entries inside
an uptrend, using a linear-regression trend channel and detected macro
support/resistance.

## Structure

```
quant_screener/
├── app.py                  # Streamlit dashboard (Deep-Dive + market scan views)
├── main.py                 # CLI scanner - run on a schedule, writes outputs/signals.csv
├── config.py                # settings, paths, secrets, ticker universe
├── data_processing.py       # yfinance fetch layer (framework-agnostic)
├── mathematical_models.py   # regression channel, S/R detection, signal score
├── discord_bot.py           # Discord webhook notifier
├── requirements.txt
├── outputs/
│   ├── favorites.json       # persisted sidebar shortcuts
│   └── signals.csv          # latest scan, produced by main.py
└── .github/workflows/main.yml  # scheduled scan + Discord alert
```

## Run the dashboard

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Run a scan manually

```bash
python main.py --notify            # scans config.DEFAULT_UNIVERSE
python main.py --tickers AAPL NVDA TSLA --min-score 60
```

## Discord alerts

Set `DISCORD_WEBHOOK_URL` either in a local `.env` file, as a
`DISCORD_WEBHOOK_URL` GitHub Actions secret, or in
`.streamlit/secrets.toml` — `config.py` checks all three.

## Model, in short

- Fits an OLS line through the last `REGRESSION_WINDOW` closes (default 90
  trading days) and draws a ±2σ channel around it (`config.CHANNEL_STD_MULT`).
- **EV Target** is the trend line's value *today* — if price sits below it,
  the model reads that as lagging its own trend (bullish); above it, as
  extended (bearish reversion risk).
- Macro **S1/R1** come from clustering swing highs/lows over the last ~2
  years (`scipy.signal.argrelextrema`).
- **Signal Score** (main.py / scan view) only scores uptrends: it rewards
  high R², price sitting near the lower half of the channel (a pullback),
  and remaining upside to the EV target.
- **Forecast** extrapolates the same trend line forward N trading days using
  the standard OLS prediction-interval formula — the confidence range widens
  the further out you project, on purpose, since that's the honest way to
  show "this is a statistical extrapolation," not a guaranteed price.
- **Entry/Stop/Target setup** anchors a buy zone on macro support (or the
  statistical lower band if no support was found), sizes the stop off the
  same residual volatility used for the channel, and reports the resulting
  Risk:Reward against the forecast target. Downtrending names (`slope <= 0`)
  get `DOWNTREND_NO_SETUP` instead of a number — this screener only looks
  for long entries inside an uptrend.

This is a technical-analysis tool for research/education, built entirely on
historical price statistics — not investment advice, and not a guarantee of
where any price will actually go.
