
# ===== CELL 0 =====
!pip install fredapi pandas matplotlib

# ===== CELL 1 =====
"""
Everstar — Consumer Stress Dashboard
=====================================
Tracks whether consumers are funding spending through savings drawdown
or credit card debt — the key question behind the retail sales divergence.

Four series:
  PSAVERT   — Personal Savings Rate (% of disposable income)
  TOTALSL   — Total Consumer Credit Outstanding ($B)
  REVOLSL   — Revolving Credit / Credit Cards ($B)
  DRCCLACBS — Credit Card Delinquency Rate (%)

Usage (Colab):
    !pip install fredapi pandas matplotlib
    # Set FRED_API_KEY in Colab Secrets (key icon in left sidebar)
    # Then run this script
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from datetime import datetime, timedelta
from fredapi import Fred
from google.colab import userdata

# ── CONFIG ────────────────────────────────────────────────────────────────────

API_KEY        = userdata.get("FRED_API_KEY")
LOOKBACK_YEARS = 10   # show decade of history for context
SMOOTH_MONTHS  = 3

SERIES = {
    "Personal Savings Rate":          ("PSAVERT",   "savings",  "neutral"),
    "Total Consumer Credit ($B)":     ("TOTALSL",   "credit",   "inverted"),
    "Revolving Credit / Cards ($B)":  ("REVOLSL",   "credit",   "inverted"),
    "Credit Card Delinquency Rate":   ("DRCCLACBS", "stress",   "inverted"),
}

COLORS = {
    "savings": "#4FC3F7",
    "credit":  "#FFB74D",
    "stress":  "#F44336",
}

# ── FETCH ─────────────────────────────────────────────────────────────────────

def fetch_all(fred, start):
    data = {}
    print(f"\n{'─'*55}")
    print(f"  Pulling consumer stress series from FRED...")
    print(f"{'─'*55}")
    for name, (sid, cat, direction) in SERIES.items():
        try:
            s = fred.get_series(sid, observation_start=start).dropna()
            data[name] = (s, cat, direction)
            print(f"  ✓  {name:<35} latest: {s.index[-1].strftime('%Y-%m-%d')}")
        except Exception as e:
            print(f"  ✗  {name:<35} FAILED: {e}")
    return data

# ── TRANSFORMS ────────────────────────────────────────────────────────────────

def yoy(s):    return s.pct_change(12) * 100
def sma(s, n): return s.rolling(n).mean()

def zscore(s):
    w = s.last("12M")
    return (s.iloc[-1] - w.mean()) / w.std() if w.std() > 0 else 0.0

# ── SUMMARY ───────────────────────────────────────────────────────────────────

def print_summary(data):
    print(f"\n{'═'*70}")
    print(f"  EVERSTAR — CONSUMER STRESS DASHBOARD")
    print(f"  Generated : {datetime.now().strftime('%A, %B %d %Y  %H:%M')}")
    print(f"{'═'*70}")

    for name, (s, cat, direction) in data.items():
        latest     = s.iloc[-1]
        latest_dt  = s.index[-1].strftime("%b %Y")
        s_yoy      = yoy(s).dropna()
        yoy_val    = s_yoy.iloc[-1] if len(s_yoy) else None
        z          = zscore(s)
        signal_z   = -z if direction == "inverted" else z
        alert      = abs(signal_z) > 1.5
        flag       = ("▲ ELEVATED" if signal_z > 0 else "▼ DEPRESSED") if alert else ""

        print(f"\n  {name}")
        print(f"  Latest ({latest_dt}): {latest:.2f}"
              + ("%" if "Rate" in name or "Saving" in name else ""))
        if yoy_val is not None:
            print(f"  YoY change : {yoy_val:+.1f}%")
        print(f"  Z-score    : {z:+.2f}  {flag}")

    # Narrative
    savings_s = data.get("Personal Savings Rate")
    revolv_s  = data.get("Revolving Credit / Cards ($B)")
    delin_s   = data.get("Credit Card Delinquency Rate")

    print(f"\n{'─'*70}")
    print(f"  STRESS NARRATIVE")
    print(f"{'─'*70}")

    signals = []
    if savings_s:
        sv = savings_s[0].iloc[-1]
        if sv < 5:
            signals.append(f"  ⚠  Savings rate at {sv:.1f}% — historically low, consumers have little buffer")
        elif sv < 8:
            signals.append(f"  →  Savings rate at {sv:.1f}% — moderate, watching for further decline")
        else:
            signals.append(f"  ✓  Savings rate at {sv:.1f}% — healthy buffer")

    if revolv_s:
        rv     = revolv_s[0]
        rv_yoy = yoy(rv).dropna()
        if len(rv_yoy) and rv_yoy.iloc[-1] > 5:
            signals.append(f"  ⚠  Revolving credit growing {rv_yoy.iloc[-1]:+.1f}% YoY — consumers borrowing to spend")
        elif len(rv_yoy) and rv_yoy.iloc[-1] > 0:
            signals.append(f"  →  Revolving credit up {rv_yoy.iloc[-1]:+.1f}% YoY — modest increase")
        else:
            signals.append(f"  ✓  Revolving credit flat/falling — no credit stress signal")

    if delin_s:
        dv = delin_s[0].iloc[-1]
        if dv > 3.0:
            signals.append(f"  ⚠  Delinquency rate at {dv:.2f}% — elevated, consumers under pressure")
        elif dv > 2.0:
            signals.append(f"  →  Delinquency rate at {dv:.2f}% — rising, worth monitoring")
        else:
            signals.append(f"  ✓  Delinquency rate at {dv:.2f}% — benign")

    for sig in signals:
        print(sig)

    # Overall verdict
    stress_count = sum(1 for s in signals if s.strip().startswith("⚠"))
    print(f"\n  Overall: {stress_count}/3 stress signals active")
    if stress_count == 3:
        print("  → HIGH STRESS: Spending slowdown likely incoming")
    elif stress_count == 2:
        print("  → MODERATE STRESS: Watch closely over next 2-3 months")
    elif stress_count == 1:
        print("  → LOW STRESS: One flag raised but not a full picture")
    else:
        print("  → NO STRESS: Consumer balance sheet appears healthy")

    print(f"{'═'*70}\n")

# ── CHARTS ────────────────────────────────────────────────────────────────────

def plot_dashboard(data, out="consumer_stress_dashboard.png"):
    """Four-panel chart: savings rate, revolving credit YoY, delinquency rate, composite."""

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.patch.set_facecolor("#0f1117")
    fig.suptitle(
        f"Everstar — Consumer Stress Dashboard  |  "
        f"{datetime.now().strftime('%B %d, %Y')}",
        fontsize=13, color="#eee", fontweight="bold", y=0.98
    )
    axes = axes.flatten()

    panels = [
        ("Personal Savings Rate",         0, False),
        ("Revolving Credit / Cards ($B)", 1, True),   # show YoY
        ("Credit Card Delinquency Rate",  2, False),
        (None,                            3, False),   # composite
    ]

    for i, (name, ax_idx, show_yoy) in enumerate(panels):
        ax = axes[ax_idx]
        ax.set_facecolor("#1a1d27")

        if name is None:
            # Panel 4: Composite stress — z-scores side by side
            names  = list(data.keys())
            zscores = []
            labels  = []
            for n, (s, cat, direction) in data.items():
                z = zscore(s)
                sz = -z if direction == "inverted" else z
                zscores.append(sz)
                labels.append(n[:30])

            colors_bar = ["#4CAF50" if z >= 0 else "#F44336" for z in zscores]
            bars = ax.barh(labels, zscores, color=colors_bar, alpha=0.8)
            ax.axvline(0, color="#666", lw=0.8)
            ax.axvline(1.5,  color="#F44336", lw=0.8, linestyle="--", alpha=0.6)
            ax.axvline(-1.5, color="#F44336", lw=0.8, linestyle="--", alpha=0.6)
            for bar, val in zip(bars, zscores):
                ax.text(val + (0.05 if val >= 0 else -0.05),
                        bar.get_y() + bar.get_height()/2,
                        f"{val:+.2f}", va="center",
                        ha="left" if val >= 0 else "right",
                        fontsize=8, color="#ccc")
            ax.set_title("Signal Z-Scores  (positive = bullish)",
                         color="#ddd", fontsize=9, pad=4)
            ax.tick_params(colors="#888", labelsize=7)
            for sp in ax.spines.values():
                sp.set_edgecolor("#333")
            continue

        if name not in data:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    color="#666", transform=ax.transAxes)
            continue

        s, cat, direction = data[name]
        color = COLORS.get(cat, "#888")

        # Trim to lookback
        cutoff = s.index[-1] - pd.DateOffset(years=LOOKBACK_YEARS)
        s_plot = s[s.index >= cutoff]

        if show_yoy:
            s_plot     = yoy(s_plot).dropna()
            s_smoothed = sma(s_plot, SMOOTH_MONTHS)
            ax.bar(s_plot.index, s_plot.values, color=color,
                   alpha=0.3, width=20)
            ax.plot(s_smoothed.index, s_smoothed.values,
                    color=color, lw=2)
            ax.axhline(0, color="#555", lw=0.8, linestyle="--")
            ylabel = "YoY %"
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
        else:
            s_smoothed = sma(s_plot, SMOOTH_MONTHS)
            ax.plot(s_plot.index, s_plot.values, color=color,
                    lw=1, alpha=0.5)
            ax.plot(s_smoothed.index, s_smoothed.values,
                    color=color, lw=2)

            # Shade danger zones
            if "Saving" in name:
                ax.axhspan(0, 4, color="#F44336", alpha=0.07)
                ax.axhline(4, color="#F44336", lw=0.7,
                           linestyle=":", alpha=0.6, label="Danger zone (<4%)")
                ax.yaxis.set_major_formatter(
                    mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
            elif "Delinquency" in name:
                ax.axhspan(2.5, ax.get_ylim()[1] if ax.get_ylim()[1] > 2.5 else 6,
                           color="#F44336", alpha=0.07)
                ax.axhline(2.5, color="#F44336", lw=0.7,
                           linestyle=":", alpha=0.6, label="Watch level (2.5%)")
                ax.yaxis.set_major_formatter(
                    mticker.FuncFormatter(lambda x, _: f"{x:.2f}%"))

        latest_str = f"{s.iloc[-1]:.2f}"
        ax.set_title(name, color="#ddd", fontsize=9, pad=4, fontweight="bold")
        ax.set_xlabel(f"Latest: {latest_str}  |  "
                      f"{s.index[-1].strftime('%b %Y')}",
                      fontsize=7, color="#888")
        ax.tick_params(colors="#666", labelsize=7)
        if ax.get_legend_handles_labels()[1]:
            ax.legend(fontsize=7, facecolor="#1a1d27", labelcolor="#aaa")
        for sp in ax.spines.values():
            sp.set_edgecolor("#333")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(out, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved → {out}")


def plot_combined(data, out="consumer_stress_combined.png"):
    """
    Combined chart showing savings rate and revolving credit YoY
    on the same axes with dual y-axis — the clearest way to see
    if consumers are substituting credit for savings.
    """
    sav  = data.get("Personal Savings Rate")
    rev  = data.get("Revolving Credit / Cards ($B)")

    if not sav or not rev:
        print("  Missing data for combined chart — skipping")
        return

    s_sav = sav[0]
    s_rev = yoy(rev[0]).dropna()

    cutoff  = min(s_sav.index[-1], s_rev.index[-1]) - pd.DateOffset(years=LOOKBACK_YEARS)
    s_sav   = s_sav[s_sav.index >= cutoff]
    s_rev   = s_rev[s_rev.index >= cutoff]

    fig, ax1 = plt.subplots(figsize=(16, 6))
    fig.patch.set_facecolor("#0f1117")
    ax1.set_facecolor("#1a1d27")

    # Savings rate on left axis
    ax1.plot(s_sav.index, s_sav.values, color="#4FC3F7", lw=2,
             label="Personal Savings Rate (L)")
    ax1.fill_between(s_sav.index, s_sav.values, 0,
                     color="#4FC3F7", alpha=0.08)
    ax1.axhline(4, color="#4FC3F7", lw=0.7, linestyle=":",
                alpha=0.5, label="Savings danger zone (4%)")
    ax1.set_ylabel("Savings Rate %", color="#4FC3F7", fontsize=9)
    ax1.tick_params(axis="y", colors="#4FC3F7", labelsize=7)
    ax1.tick_params(axis="x", colors="#666", labelsize=7)
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))

    # Revolving credit YoY on right axis
    ax2 = ax1.twinx()
    ax2.plot(s_rev.index, s_rev.values, color="#FFB74D", lw=2,
             label="Revolving Credit YoY % (R)")
    ax2.axhline(0, color="#555", lw=0.8, linestyle="--")
    ax2.fill_between(s_rev.index, s_rev.values, 0,
                     where=(s_rev.values > 0),
                     color="#FFB74D", alpha=0.08, interpolate=True)
    ax2.set_ylabel("Revolving Credit YoY %", color="#FFB74D", fontsize=9)
    ax2.tick_params(axis="y", colors="#FFB74D", labelsize=7)
    ax2.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))

    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2,
               fontsize=8, facecolor="#1a1d27", labelcolor="#aaa",
               loc="upper left")

    ax1.set_title(
        "Consumer Stress: Savings Rate vs Credit Card Growth\n"
        "When savings falls and credit rises simultaneously → consumers funding spending on debt",
        color="#ddd", fontsize=11, fontweight="bold"
    )
    for sp in ax1.spines.values():
        sp.set_edgecolor("#333")

    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved → {out}")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    fred  = Fred(api_key=API_KEY)
    start = (datetime.now() - timedelta(days=365 * LOOKBACK_YEARS)).strftime("%Y-%m-%d")

    data = fetch_all(fred, start)

    if not data:
        print("  No data retrieved — check API key")
        return

    print_summary(data)
    plot_dashboard(data)
    plot_combined(data)

    print(f"\n  Done. Two charts generated:")
    print(f"    consumer_stress_dashboard.png — four-panel overview")
    print(f"    consumer_stress_combined.png  — savings vs credit card side by side\n")

    try:
        from IPython.display import Image, display
        for f in ["consumer_stress_dashboard.png",
                  "consumer_stress_combined.png"]:
            display(Image(f))
    except ImportError:
        pass


if __name__ == "__main__":
    main()