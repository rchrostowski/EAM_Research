
# ===== CELL 0 =====
!pip install pandas openpyxl matplotlib requests

# ===== CELL 1 =====
"""
Everstar — Census Monthly Retail Trade Sales Dashboard v3
=========================================================
Ben's favorite leading indicator for the U.S. economy.

Fix in v3: detect actual month columns from header row to avoid
picking up CY CUM / PY CUM columns that were spiking the charts.

Usage (Colab):
    !pip install pandas openpyxl matplotlib requests
    # No API key needed — fully public Census Bureau data
"""

import warnings
warnings.filterwarnings("ignore")

import io
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────

URL            = "https://www.census.gov/retail/mrts/www/mrtssales92-present.xlsx"
LOOKBACK_YEARS = 5
SMOOTH_MONTHS  = 3

MONTH_COLS = ["Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec"]

KEY_CATEGORIES = [
    "Retail and food services sales, total",
    "Retail sales, total",
    "Motor vehicle and parts dealers",
    "Furniture and home furnishings stores",
    "Electronics and appliance stores",
    "Food and beverage stores",
    "Gasoline stations",
    "Clothing and clothing accessories stores",
    "Sporting goods, hobby, musical instrument, and book stores",
    "General merchandise stores",
    "Nonstore retailers",
    "Food services and drinking places",
]

# ── FETCH ─────────────────────────────────────────────────────────────────────

def fetch_excel(url):
    print("  Downloading from Census Bureau...")
    headers = {"User-Agent": "Everstar Research everstar@gmail.com"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    print(f"  Downloaded {len(r.content)/1024:.0f} KB")
    return r.content

# ── PARSE ─────────────────────────────────────────────────────────────────────

def parse_one_sheet(xl, year):
    """
    Parse a single year sheet.
    Layout:
      col 0 = NAICS code
      col 1 = category name
      row 4 = month headers ("Jan. 2026", "Feb. 2026", etc.)
      row 6+ = data rows

    Key fix: detect actual month columns from the header row so we
    never accidentally read CY CUM / PY CUM as monthly data.
    """
    try:
        raw = pd.read_excel(xl, sheet_name=str(year),
                            header=None, engine="openpyxl")
    except Exception:
        return []

    # Find which columns are actual months from header row (row 4)
    header = raw.iloc[4]
    month_col_map = {}  # {month_index 0-11: col_index}
    for col_idx, val in enumerate(header):
        val_str = str(val).strip()
        for m_idx, m in enumerate(MONTH_COLS):
            if val_str.startswith(m):
                month_col_map[m_idx] = col_idx
                break

    if not month_col_map:
        return []

    # Data rows start at row 6
    records = []
    for _, row in raw.iloc[6:].iterrows():
        cat = str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else ""
        if not cat or cat in ["nan", "None", "NaN"]:
            continue
        if cat.startswith("(") or cat.startswith("[") or len(cat) < 5:
            continue

        monthly = {}
        for m_idx, col_idx in month_col_map.items():
            try:
                v = float(row.iloc[col_idx])
                if v > 0:
                    monthly[pd.Timestamp(year=year, month=m_idx+1, day=1)] = v
            except (ValueError, TypeError):
                pass

        if monthly:
            records.append({"category": cat, "monthly": monthly})

    return records


def build_series(content):
    """Loop all year sheets and stitch into {category: pd.Series}."""
    xl    = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
    years = sorted([int(s) for s in xl.sheet_names if s.isdigit()])
    print(f"  Found {len(years)} year sheets: {years[0]}–{years[-1]}")

    all_data = {}
    for year in years:
        for rec in parse_one_sheet(xl, year):
            cat = rec["category"]
            if cat not in all_data:
                all_data[cat] = {}
            all_data[cat].update(rec["monthly"])

    series_dict = {}
    for cat, date_vals in all_data.items():
        s = pd.Series(date_vals).sort_index()
        s = s[s > 0]
        if len(s) >= 12:
            series_dict[cat] = s

    print(f"  Built {len(series_dict)} category time series")
    return series_dict

# ── TRANSFORMS ────────────────────────────────────────────────────────────────

def yoy(s):    return s.pct_change(12) * 100
def mom(s):    return s.pct_change(1)  * 100
def sma(s, n): return s.rolling(n).mean()

# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_total(series_dict):
    for k in series_dict:
        if "Retail and food services sales, total" in k:
            return series_dict[k]
    return series_dict[next(iter(series_dict))]


def get_cat(series_dict, label):
    return next((series_dict[k] for k in series_dict
                 if label.lower() in k.lower()), None)

# ── SUMMARY ───────────────────────────────────────────────────────────────────

def print_summary(series_dict):
    s         = get_total(series_dict).dropna()
    s_yoy     = yoy(s).dropna()
    s_mom     = mom(s).dropna()
    s_3mma    = sma(s, SMOOTH_MONTHS)
    s_ysmooth = sma(s_yoy, SMOOTH_MONTHS).dropna()

    print(f"\n{'═'*70}")
    print(f"  EVERSTAR — CENSUS MONTHLY RETAIL TRADE DASHBOARD")
    print(f"  Generated : {datetime.now().strftime('%A, %B %d %Y  %H:%M')}")
    print(f"{'═'*70}")
    print(f"\n  Latest month   : {s.index[-1].strftime('%B %Y')}")
    print(f"  Sales ($M)     : ${s.iloc[-1]:>12,.0f}")
    print(f"  YoY change     : {s_yoy.iloc[-1]:>+.1f}%")
    print(f"  MoM change     : {s_mom.iloc[-1]:>+.1f}%")
    print(f"  3-Month MA     : ${s_3mma.dropna().iloc[-1]:>12,.0f}")

    if len(s_ysmooth) >= 3:
        tail = s_ysmooth.iloc[-3:]
        if tail.is_monotonic_increasing:
            trend = "↑ ACCELERATING"
        elif tail.is_monotonic_decreasing:
            trend = "↓ DECELERATING"
        else:
            trend = "→ MIXED"
        print(f"  Trend signal   : {trend}  (smoothed YoY)")

    print(f"\n{'─'*70}")
    print(f"  KEY CATEGORIES — Latest YoY %")
    print(f"{'─'*70}")
    for cat in KEY_CATEGORIES:
        s_cat = get_cat(series_dict, cat)
        if s_cat is not None:
            y = yoy(s_cat).dropna()
            if len(y):
                arrow = "▲" if y.iloc[-1] >= 0 else "▼"
                key   = next(k for k in series_dict if cat.lower() in k.lower())
                print(f"  {arrow} {y.iloc[-1]:>+6.1f}%  {key[:55]}")

    print(f"{'═'*70}\n")

# ── CHARTS ────────────────────────────────────────────────────────────────────

def plot_dashboard(series_dict, out="retail_sales_dashboard.png"):
    s      = get_total(series_dict).dropna()
    cutoff = s.index[-1] - pd.DateOffset(years=LOOKBACK_YEARS)
    s      = s[s.index >= cutoff]

    s_yoy      = yoy(s)
    s_mom      = mom(s)
    s_3mma     = sma(s, SMOOTH_MONTHS)
    s_yoy_3mma = sma(s_yoy, SMOOTH_MONTHS)

    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=False)
    fig.patch.set_facecolor("#0f1117")
    fig.suptitle(
        f"Everstar — Census Monthly Retail Trade  |  "
        f"Latest: {s.index[-1].strftime('%B %Y')}",
        fontsize=13, color="#eee", fontweight="bold", y=0.98
    )

    # Panel 1: Raw + 3MMA
    ax = axes[0]
    ax.set_facecolor("#1a1d27")
    ax.plot(s.index, s.values, color="#4FC3F7", lw=1,
            alpha=0.5, label="Monthly Sales")
    ax.plot(s_3mma.index, s_3mma.values, color="#FFB74D",
            lw=2, label=f"{SMOOTH_MONTHS}-Month MA")
    ax.set_title("Total Retail & Food Services Sales ($M)",
                 color="#ddd", fontsize=10, pad=4)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x/1000:.0f}B"))
    ax.legend(fontsize=8, facecolor="#1a1d27", labelcolor="#aaa")
    ax.tick_params(colors="#666", labelsize=7)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333")

    # Panel 2: YoY + smoothed
    ax = axes[1]
    ax.set_facecolor("#1a1d27")
    ax.bar(s_yoy.index, s_yoy.values, color="#81C784",
           alpha=0.35, width=20, label="YoY %")
    ax.plot(s_yoy_3mma.index, s_yoy_3mma.values, color="#F44336",
            lw=2.5, label=f"Smoothed YoY ({SMOOTH_MONTHS}MMA) ← Ben's signal")
    ax.axhline(0, color="#555", lw=0.8, linestyle="--")
    ax.set_title("Year-over-Year % Change", color="#ddd", fontsize=10, pad=4)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.legend(fontsize=8, facecolor="#1a1d27", labelcolor="#aaa")
    ax.tick_params(colors="#666", labelsize=7)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333")

    # Panel 3: MoM
    ax = axes[2]
    ax.set_facecolor("#1a1d27")
    s_mom_clean = s_mom.dropna()
    bar_cols = ["#4CAF50" if v >= 0 else "#F44336"
                for v in s_mom_clean.values]
    ax.bar(s_mom_clean.index, s_mom_clean.values,
           color=bar_cols, alpha=0.75, width=20)
    ax.axhline(0, color="#555", lw=0.8, linestyle="--")
    ax.set_title("Month-over-Month % Change",
                 color="#ddd", fontsize=10, pad=4)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))
    ax.tick_params(colors="#666", labelsize=7)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333")

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig(out, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved → {out}")


def plot_ben_signal(series_dict, out="retail_ben_signal.png"):
    s          = get_total(series_dict).dropna()
    s_yoy      = yoy(s).dropna()
    s_yoy_3mma = sma(s_yoy, SMOOTH_MONTHS)

    recessions = [
        ("2001-03-01", "2001-11-01"),
        ("2007-12-01", "2009-06-01"),
        ("2020-02-01", "2020-04-01"),
    ]

    fig, ax = plt.subplots(figsize=(16, 6))
    fig.patch.set_facecolor("#0f1117")
    ax.set_facecolor("#1a1d27")

    for start, end in recessions:
        ax.axvspan(pd.Timestamp(start), pd.Timestamp(end),
                   color="#F44336", alpha=0.12)

    ax.plot(s_yoy.index, s_yoy.values, color="#4FC3F7",
            lw=0.8, alpha=0.4, label="YoY %")
    ax.plot(s_yoy_3mma.index, s_yoy_3mma.values, color="#FFB74D",
            lw=2.5, label=f"Smoothed YoY ({SMOOTH_MONTHS}MMA) — Ben's signal")
    ax.axhline(0, color="#666", lw=1, linestyle="--")

    s_yoy_3mma_vals = s_yoy_3mma.dropna()
    ax.fill_between(s_yoy_3mma_vals.index, s_yoy_3mma_vals.values, 0,
                    where=(s_yoy_3mma_vals.values >= 0),
                    color="#4CAF50", alpha=0.1, interpolate=True)
    ax.fill_between(s_yoy_3mma_vals.index, s_yoy_3mma_vals.values, 0,
                    where=(s_yoy_3mma_vals.values < 0),
                    color="#F44336", alpha=0.1, interpolate=True)

    ax.set_title(
        "Census Retail Sales — Ben's Leading Indicator\n"
        "Smoothed YoY % Change (3MMA)  |  Red shading = NBER recessions",
        color="#ddd", fontsize=11, fontweight="bold"
    )
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.tick_params(colors="#888", labelsize=8)
    ax.legend(fontsize=9, facecolor="#1a1d27", labelcolor="#aaa")
    for sp in ax.spines.values():
        sp.set_edgecolor("#333")

    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved → {out}")


def plot_categories(series_dict, out="retail_sales_categories.png"):
    cats = []
    for cat in KEY_CATEGORIES:
        s_cat = get_cat(series_dict, cat)
        if s_cat is not None:
            key = next(k for k in series_dict if cat.lower() in k.lower())
            cats.append((cat, key))

    if not cats:
        print("  No key categories matched — skipping category chart")
        return

    n = len(cats)
    cols = 3
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(16, rows * 3.2))
    fig.patch.set_facecolor("#0f1117")
    fig.suptitle(
        "Everstar — Retail Sales by Category  |  YoY % (Smoothed)",
        fontsize=13, color="#eee", fontweight="bold", y=1.01
    )
    axes = axes.flatten()

    for i, (label, key) in enumerate(cats):
        ax = axes[i]
        ax.set_facecolor("#1a1d27")

        s      = series_dict[key].dropna()
        cutoff = s.index[-1] - pd.DateOffset(years=LOOKBACK_YEARS)
        s      = s[s.index >= cutoff]

        s_yoy      = yoy(s)
        s_yoy_3mma = sma(s_yoy, SMOOTH_MONTHS)
        latest_yoy = s_yoy.dropna().iloc[-1] if len(s_yoy.dropna()) else np.nan

        color = "#4CAF50" if (not np.isnan(latest_yoy) and latest_yoy >= 0) \
                else "#F44336"

        ax.bar(s_yoy.index, s_yoy.values,
               color=color, alpha=0.3, width=20)
        ax.plot(s_yoy_3mma.index, s_yoy_3mma.values,
                color=color, lw=1.8)
        ax.axhline(0, color="#555", lw=0.7, linestyle="--")

        ax.set_title(label[:42], fontsize=7.5, color="#ddd",
                     pad=3, fontweight="bold")
        yoy_str = f"{latest_yoy:+.1f}%" if not np.isnan(latest_yoy) else "N/A"
        ax.set_xlabel(f"Latest YoY: {yoy_str}", fontsize=7, color="#888")
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
        ax.tick_params(colors="#666", labelsize=6)
        for sp in ax.spines.values():
            sp.set_edgecolor("#333")

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout(pad=1.5)
    plt.savefig(out, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved → {out}")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'─'*70}")
    print(f"  Census Monthly Retail Trade Sales — Everstar Dashboard v3")
    print(f"  Source: census.gov/retail/sales.html")
    print(f"{'─'*70}")

    content     = fetch_excel(URL)
    series_dict = build_series(content)

    if not series_dict:
        print("\n  ERROR: No data parsed.")
        return

    print_summary(series_dict)
    plot_dashboard(series_dict)
    plot_ben_signal(series_dict)
    plot_categories(series_dict)

    print(f"\n  Done. Three charts generated:")
    print(f"    retail_sales_dashboard.png  — total sales, YoY, MoM")
    print(f"    retail_ben_signal.png       — Ben's leading indicator vs recessions")
    print(f"    retail_sales_categories.png — breakdown by sub-sector\n")

    try:
        from IPython.display import Image, display
        for f in ["retail_sales_dashboard.png",
                  "retail_ben_signal.png",
                  "retail_sales_categories.png"]:
            display(Image(f))
    except ImportError:
        pass


if __name__ == "__main__":
    main()

# ===== CELL 2 =====
