
# ===== CELL 0 =====
!pip install fredapi pandas matplotlib seaborn
"""
Everstar — FRED Alternative Data Dashboard
=========================================
Pulls high-frequency economic series from FRED and prints a
weekly monitoring summary. Flags series that are moving in a
concerning direction.

Usage:
    1. Get a free API key at https://fredaccount.stlouisfed.org/apikeys
    2. Replace YOUR_API_KEY_HERE below (or set env var FRED_API_KEY)
    3. Run: python fred_dashboard.py

Requires: pip install fredapi pandas matplotlib seaborn
"""

import os
import sys
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from fredapi import Fred
from datetime import datetime, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
from google.colab import userdata
API_KEY = userdata.get('FRED_API_KEY')

# How far back to pull data (years)
LOOKBACK_YEARS = 3

# Flag threshold: how many std deviations from recent mean = alert
ALERT_THRESHOLD = 1.5

# ── SERIES DEFINITIONS ────────────────────────────────────────────────────────

SERIES = {
    # --- Supply Chain & Trade ---
    "Rail Carloads (Total)":        ("RAILFRTCARLOADSD11","supply_chain",  "neutral"),
    "Rail Intermodal Units":        ("RAILFRTINTERMODAL",          "supply_chain",  "neutral"),
    "Freight Transport Index":      ("TSIFRGHT",          "supply_chain",  "neutral"),

    # --- Industrial Activity ---
    "Industrial Production":        ("INDPRO",            "industrial",    "neutral"),
    "Capacity Utilization (Mfg)":   ("CAPUTLB00004SQ",   "industrial",    "neutral"),
    "Durable Goods New Orders":     ("AMTMNO",            "industrial",    "neutral"),
    "Mfg New Orders":               ("MNFCTRSMSA",        "industrial",    "neutral"),

    # --- Consumer / Retail ---
    "Retail Sales ex Food & Gas":   ("RSXFS",             "consumer",      "neutral"),
    "Consumer Sentiment (UMich)":   ("UMCSENT",           "consumer",      "neutral"),
    "Real Disposable Income":       ("DSPIC96",           "consumer",      "neutral"),

    # --- Energy ---
    "WTI Crude Oil (Daily)":        ("DCOILWTICO",        "energy",        "neutral"),
    "Henry Hub Natural Gas":        ("DHHNGSP",           "energy",        "neutral"),

    # --- Labor Market ---
    "Initial Jobless Claims":       ("ICSA",              "labor",         "inverted"),
    "Continuing Claims":            ("CCSA",              "labor",         "inverted"),
    "Job Openings (JOLTS)":         ("JTSJOL",            "labor",         "neutral"),

    # --- Credit & Financial Conditions ---
    "HY Credit Spread":             ("BAMLH0A0HYM2",      "credit",        "inverted"),
    "STL Financial Stress Index":   ("STLFSI4",           "credit",        "inverted"),

    # --- Composite / Nowcast ---
    "NY Fed Weekly Econ Index":     ("WEI",               "composite",     "neutral"),
}

CATEGORY_COLORS = {
    "supply_chain": "#2196F3",
    "industrial":   "#FF9800",
    "consumer":     "#4CAF50",
    "energy":       "#9C27B0",
    "labor":        "#F44336",
    "credit":       "#795548",
    "composite":    "#009688",
}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def fetch_all(fred: Fred, start: str) -> dict:
    """Pull all series from FRED, return dict of {name: Series}."""
    data = {}
    failed = []
    print(f"\n{'─'*55}")
    print(f"  Pulling {len(SERIES)} series from FRED...")
    print(f"{'─'*55}")
    for name, (series_id, category, direction) in SERIES.items():
        try:
            s = fred.get_series(series_id, observation_start=start)
            s = s.dropna()
            data[name] = s
            latest_date = s.index[-1].strftime("%Y-%m-%d")
            print(f"  ✓  {name:<35} latest: {latest_date}")
        except Exception as e:
            failed.append((name, series_id, str(e)))
            print(f"  ✗  {name:<35} FAILED ({series_id})")
    if failed:
        print(f"\n  {len(failed)} series failed to load — check API key or series ID.")
    return data


def compute_signal(series: pd.Series, direction: str) -> dict:
    """
    Compute a simple signal for the series:
    - latest value vs 3-month ago
    - latest value vs 1-year ago
    - z-score vs trailing 52-week window
    - direction flag: 'inverted' means down = bad (e.g. claims rising = bad)
    """
    if len(series) < 4:
        return {}

    latest      = series.iloc[-1]
    date_latest = series.index[-1]

    # 3-month change (approx 13 weeks back)
    idx_3m = series.index.get_indexer([date_latest - timedelta(days=90)], method="nearest")[0]
    val_3m = series.iloc[idx_3m]
    chg_3m = (latest - val_3m) / abs(val_3m) * 100 if val_3m != 0 else None

    # 1-year change
    idx_1y = series.index.get_indexer([date_latest - timedelta(days=365)], method="nearest")[0]
    val_1y = series.iloc[idx_1y]
    chg_1y = (latest - val_1y) / abs(val_1y) * 100 if val_1y != 0 else None

    # Z-score vs 52-week window
    window = series.last("52W")
    z = (latest - window.mean()) / window.std() if window.std() > 0 else 0

    # Flip z for inverted series
    signal_z = -z if direction == "inverted" else z

    # Alert if |z| > threshold
    alert = abs(signal_z) > ALERT_THRESHOLD
    bullish = signal_z > 0

    return {
        "latest":    latest,
        "date":      date_latest.strftime("%Y-%m-%d"),
        "chg_3m":   chg_3m,
        "chg_1y":   chg_1y,
        "z":         z,
        "signal_z":  signal_z,
        "alert":     alert,
        "bullish":   bullish,
    }


def print_summary(data: dict):
    """Print a formatted terminal summary grouped by category."""
    print(f"\n{'═'*70}")
    print(f"  EVERSTAR — FRED MACRO DASHBOARD")
    print(f"  Generated: {datetime.now().strftime('%A, %B %d %Y  %H:%M')}")
    print(f"{'═'*70}")

    # Group by category
    by_cat = {}
    for name, (sid, cat, direction) in SERIES.items():
        by_cat.setdefault(cat, []).append((name, direction))

    cat_labels = {
        "supply_chain": "SUPPLY CHAIN & TRADE",
        "industrial":   "INDUSTRIAL ACTIVITY",
        "consumer":     "CONSUMER & RETAIL",
        "energy":       "ENERGY",
        "labor":        "LABOR MARKET",
        "credit":       "CREDIT & FINANCIAL CONDITIONS",
        "composite":    "COMPOSITE / NOWCAST",
    }

    alerts = []

    for cat, items in by_cat.items():
        print(f"\n  ── {cat_labels.get(cat, cat.upper())} {'─'*(48-len(cat_labels.get(cat,cat)))}")
        print(f"  {'Series':<35} {'Latest':>10}  {'3M Chg':>8}  {'1Y Chg':>8}  {'Signal':>8}")
        print(f"  {'─'*35} {'─'*10}  {'─'*8}  {'─'*8}  {'─'*8}")

        for name, direction in items:
            if name not in data:
                print(f"  {name:<35} {'N/A':>10}")
                continue

            sig = compute_signal(data[name], direction)
            if not sig:
                continue

            latest_str = f"{sig['latest']:>10.2f}"
            chg3m_str  = f"{sig['chg_3m']:>+7.1f}%" if sig['chg_3m'] is not None else "    N/A"
            chg1y_str  = f"{sig['chg_1y']:>+7.1f}%" if sig['chg_1y'] is not None else "    N/A"

            if sig["alert"]:
                arrow = "▲" if sig["bullish"] else "▼"
                flag  = f" {arrow} ALERT"
                alerts.append((name, sig))
            else:
                flag = ""

            print(f"  {name:<35} {latest_str}  {chg3m_str}  {chg1y_str}  {flag}")

    # Alert summary
    print(f"\n{'═'*70}")
    if alerts:
        print(f"  ⚠  {len(alerts)} SERIES FLAGGED THIS WEEK")
        print(f"{'─'*70}")
        for name, sig in alerts:
            direction_word = "ELEVATED" if sig["bullish"] else "DEPRESSED"
            arrow = "▲" if sig["bullish"] else "▼"
            print(f"  {arrow}  {name:<35}  z={sig['z']:+.2f}  → {direction_word}")
    else:
        print(f"  ✓  No series outside normal range this week.")
    print(f"{'═'*70}\n")

    return alerts


def plot_dashboard(data: dict, output_path: str = "fred_dashboard.png"):
    """Generate a multi-panel chart of all series."""
    n = len(data)
    cols = 3
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(18, rows * 3.2))
    fig.patch.set_facecolor("#0f1117")
    axes = axes.flatten()

    for i, (name, (sid, cat, direction)) in enumerate(SERIES.items()):
        ax = axes[i]
        ax.set_facecolor("#1a1d27")

        if name not in data or data[name].empty:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    color="#666", transform=ax.transAxes)
            ax.set_title(name, fontsize=8, color="#aaa")
            continue

        s = data[name]
        color = CATEGORY_COLORS.get(cat, "#888")

        # Plot line
        ax.plot(s.index, s.values, color=color, linewidth=1.2, alpha=0.9)

        # Shade 52-week range
        window = s.last("52W")
        ax.axhspan(window.min(), window.max(), alpha=0.08, color=color)
        ax.axhline(window.mean(), color=color, linewidth=0.5, linestyle="--", alpha=0.5)

        # Latest dot
        ax.scatter(s.index[-1], s.iloc[-1], color=color, s=25, zorder=5)

        # Signal z-score compute
        sig = compute_signal(s, direction)
        if sig and sig["alert"]:
            border_color = "#4CAF50" if sig["bullish"] else "#F44336"
            for spine in ax.spines.values():
                spine.set_edgecolor(border_color)
                spine.set_linewidth(2)
        else:
            for spine in ax.spines.values():
                spine.set_edgecolor("#333")
                spine.set_linewidth(0.5)

        # Labels
        ax.set_title(name, fontsize=8, color="#ddd", pad=4, fontweight="bold")
        ax.tick_params(colors="#666", labelsize=6)
        ax.xaxis.set_tick_params(rotation=30)

        latest_str = f"{s.iloc[-1]:.1f}"
        chg_str = ""
        if sig and sig["chg_1y"] is not None:
            chg_str = f"  YoY: {sig['chg_1y']:+.1f}%"
        ax.set_xlabel(f"Latest: {latest_str}{chg_str}", fontsize=6, color="#888")

        # Category label pill
        ax.text(0.02, 0.97, cat.replace("_", " ").upper(),
                transform=ax.transAxes, fontsize=5,
                color=color, alpha=0.8, va="top")

    # Hide unused axes
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle(
        f"Everstar — FRED Macro Dashboard  |  {datetime.now().strftime('%B %d, %Y')}",
        fontsize=13, color="#eee", fontweight="bold", y=1.01
    )
    plt.tight_layout(pad=1.5)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Chart saved → {output_path}")


def plot_convergence(data: dict, alerts: list, output_path: str = "fred_convergence.png"):
    """
    Convergence chart: shows z-scores for all series on one axis.
    When multiple series move together it's the strongest signal.
    """
    records = []
    for name, (sid, cat, direction) in SERIES.items():
        if name not in data:
            continue
        sig = compute_signal(data[name], direction)
        if not sig:
            continue
        records.append({
            "Series":   name,
            "Category": cat,
            "Z-Score":  round(sig["signal_z"], 2),
            "Alert":    sig["alert"],
        })

    df = pd.DataFrame(records).sort_values("Z-Score")

    fig, ax = plt.subplots(figsize=(12, max(6, len(df) * 0.42)))
    fig.patch.set_facecolor("#0f1117")
    ax.set_facecolor("#1a1d27")

    colors = [
        ("#4CAF50" if r["Z-Score"] > 0 else "#F44336") if r["Alert"]
        else ("#2E7D32" if r["Z-Score"] > 0 else "#B71C1C")
        for _, r in df.iterrows()
    ]

    bars = ax.barh(df["Series"], df["Z-Score"], color=colors, alpha=0.85, height=0.6)

    ax.axvline(0, color="#666", linewidth=0.8)
    ax.axvline(ALERT_THRESHOLD, color="#F44336", linewidth=0.8,
               linestyle="--", alpha=0.5, label=f"Alert threshold (±{ALERT_THRESHOLD}σ)")
    ax.axvline(-ALERT_THRESHOLD, color="#F44336", linewidth=0.8, linestyle="--", alpha=0.5)

    ax.set_xlabel("Signal Z-Score  (positive = bullish, negative = bearish)", color="#aaa", fontsize=9)
    ax.set_title(
        f"Everstar — Signal Convergence  |  {datetime.now().strftime('%B %d, %Y')}\n"
        "Bars outside dashed lines = flagged this week",
        color="#ddd", fontsize=11, fontweight="bold"
    )
    ax.tick_params(colors="#aaa", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")

    # Add value labels
    for bar, val in zip(bars, df["Z-Score"]):
        ax.text(
            val + (0.05 if val >= 0 else -0.05),
            bar.get_y() + bar.get_height() / 2,
            f"{val:+.2f}",
            va="center",
            ha="left" if val >= 0 else "right",
            fontsize=7, color="#ccc"
        )

    ax.legend(fontsize=8, facecolor="#1a1d27", labelcolor="#aaa")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Convergence chart saved → {output_path}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if API_KEY == "YOUR_API_KEY_HERE":
        print("\n  ERROR: No FRED API key set.")
        print("  Get one free at: https://fredaccount.stlouisfed.org/apikeys")
        print("  Then either:")
        print("    export FRED_API_KEY=your_key   (recommended)")
        print("    or edit API_KEY in this script\n")
        sys.exit(1)

    fred  = Fred(api_key=API_KEY)
    start = (datetime.now() - timedelta(days=365 * LOOKBACK_YEARS)).strftime("%Y-%m-%d")

    # 1. Pull data
    data = fetch_all(fred, start)

    # 2. Terminal summary + alerts
    alerts = print_summary(data)

    # 3. Multi-panel time series chart
    plot_dashboard(data, output_path="fred_dashboard.png")
    plot_convergence(data, alerts, output_path="fred_convergence.png")

    print(f"\n  Done. Two charts generated:")
    print(f"    fred_dashboard.png    — time series for all series")
    print(f"    fred_convergence.png  — signal strength comparison\n")


if __name__ == "__main__":
    main()


# ===== CELL 1 =====
from IPython.display import Image, display
display(Image('fred_dashboard.png'))
display(Image('fred_convergence.png'))