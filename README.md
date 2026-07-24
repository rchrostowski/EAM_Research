# Everstar Alternative Data Dashboard

Six-page Streamlit dashboard built from the supplied research notebooks.

## Pages
1. Macro Overview — FRED 18-series dashboard, convergence chart, weekly pulse.
2. Consumer Health — Census retail sales plus FRED savings/credit/delinquency series.
3. Supply Chain — placeholder until the dedicated AAR / BDI / FBX pipeline is connected.
4. Insider Activity — SEC Form 4 scanner with lookback and transaction thresholds.
5. Corporate Stress — WARN Act scanner plus SEC 8-K monitor.
6. Market Signals — placeholder until Kalshi / CapitolTrades feeds are connected.

## Run locally
```bash
pip install -r requirements.txt
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit secrets.toml
streamlit run app.py
```

## Streamlit Cloud secrets
Add:
```toml
FRED_API_KEY = "..."
SEC_IDENTITY = "Your Name your.email@example.com"
```

The dashboard does not generate discretionary investment commentary. It displays source data and the threshold/signal rules carried over from the supplied notebooks.
