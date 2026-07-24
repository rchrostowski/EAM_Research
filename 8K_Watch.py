
# ===== CELL 0 =====
!pip install requests pandas

# ===== CELL 1 =====
"""
Everstar — 8-K Material Event Monitor
=======================================
Monitors SEC EDGAR for 8-K filings across your watchlist.
8-Ks must be filed within 4 business days of a material event —
making them one of the highest-frequency signals available.

Key 8-K items to watch:
  1.01 — Entry into material agreement
  1.02 — Termination of material agreement
  1.03 — Bankruptcy / receivership
  2.01 — Completion of acquisition or disposition
  2.02 — Results of operations (earnings releases)
  2.04 — Triggering events for accelerated debt
  2.05 — Cost-associated restructuring (layoffs)
  2.06 — Material impairment
  4.01 — Auditor change (red flag)
  4.02 — Non-reliance on financial statements (red flag)
  5.02 — Departure/appointment of directors or officers
  7.01 — Regulation FD disclosure
  8.01 — Other events

Source: SEC EDGAR full-text search API (free, no key needed)
Docs:   https://efts.sec.gov/LATEST/search-index

Usage (Colab):
    !pip install requests pandas
    # No API key needed
"""

import warnings
warnings.filterwarnings("ignore")

import time
import requests
import pandas as pd
from datetime import datetime, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────

# Tickers to monitor — maps ticker to CIK number
# CIK is SEC's internal company identifier
# Find any CIK at: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=TICKER
WATCHLIST = {
    # ── Mega-cap tech ────────────────────────────────────────────────────
    "AAPL":  "0000320193",
    "MSFT":  "0000789019",
    "GOOGL": "0001652044",
    "META":  "0001326801",
    "AMZN":  "0001018724",
    "NVDA":  "0001045810",
    "TSLA":  "0001318605",
    "NFLX":  "0001065280",
    "ADBE":  "0000796343",
    "CRM":   "0001108524",
    "ORCL":  "0001341439",
    "CSCO":  "0000858877",
    "INTC":  "0000050863",
    "AMD":   "0000002488",
    "IBM":   "0000051143",

    # ── Financials ───────────────────────────────────────────────────────
    "JPM":   "0000019617",
    "BAC":   "0000070858",
    "WFC":   "0000072971",
    "GS":    "0000886982",
    "MS":    "0000895421",
    "C":     "0000831001",
    "AXP":   "0000004962",
    "COF":   "0000927628",
    "USB":   "0000036104",
    "PNC":   "0000713676",

    # ── Industrials ──────────────────────────────────────────────────────
    "CMC":   "0000022444",
    "NUE":   "0000073309",
    "STLD":  "0001022671",
    "CLF":   "0000764065",
    "CAT":   "0000018230",
    "DE":    "0000315189",
    "EMR":   "0000032604",
    "GXO":   "0001852244",
    "UNP":   "0000100885",
    "NSC":   "0000702165",

    # ── Energy ───────────────────────────────────────────────────────────
    "XOM":   "0000034088",
    "CVX":   "0000093410",
    "COP":   "0001163165",
    "PSX":   "0001534701",
    "VLO":   "0001035002",
    "MPC":   "0001510295",
    "OXY":   "0000797468",
    "HAL":   "0000045012",
    "SLB":   "0000087347",
    "BKR":   "0001831631",

    # ── Healthcare ───────────────────────────────────────────────────────
    "JNJ":   "0000200406",
    "PFE":   "0000078003",
    "MRK":   "0000310158",
    "ABBV":  "0001551152",
    "LLY":   "0000059478",
    "BMY":   "0000014272",
    "AMGN":  "0000820081",
    "GILD":  "0000882095",
    "UNH":   "0000731766",
    "REGN":  "0000872589",

    # ── Consumer ─────────────────────────────────────────────────────────
    "WMT":   "0000104169",
    "TGT":   "0000027419",
    "COST":  "0000909832",
    "MCD":   "0000063754",
    "SBUX":  "0000829224",
    "NKE":   "0000320187",
    "HD":    "0000354950",
    "LOW":   "0000060667",
    "KR":    "0000056873",
    "WBA":   "0001608249",

    # ── Telecom & Media ──────────────────────────────────────────────────
    "VZ":    "0000732712",
    "T":     "0000732717",
    "CMCSA": "0001166691",
    "DIS":   "0001001039",
    "PARA":  "0000813828",

    # ── Mid-cap watchlist ────────────────────────────────────────────────
    "CMC":   "0000022444",
    "POWL":  "0000081362",
    "INGR":  "0000049754",
    "PRGO":  "0001585583",
    "HALO":  "0001159036",
    "FORM":  "0001039399",
    "COHU":  "0000021535",
}

# How many days back to scan
LOOKBACK_DAYS = 14

# 8-K items that are most investment-relevant (flag these prominently)
HIGH_SIGNAL_ITEMS = {
    "1.01": "Material Agreement Entered",
    "1.02": "Material Agreement Terminated",
    "1.03": "Bankruptcy / Receivership",
    "2.01": "Acquisition or Disposition Completed",
    "2.04": "Debt Default / Acceleration Trigger",
    "2.05": "Restructuring / Layoffs",
    "2.06": "Material Impairment",
    "4.01": "⚠ Auditor Change",
    "4.02": "⚠ Non-Reliance on Financials",
    "5.02": "Executive / Director Change",
    "8.01": "Other Material Event",
}

STANDARD_ITEMS = {
    "2.02": "Earnings Release",
    "7.01": "Regulation FD Disclosure",
    "9.01": "Financial Statements",
}

HEADERS = {
    "User-Agent": "Everstar Research everstar@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

BASE_URL = "https://data.sec.gov"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

# ── FETCH ─────────────────────────────────────────────────────────────────────

def get_company_filings(cik: str, ticker: str, start_date: str) -> list:
    """
    Pull recent 8-K filings for a company using EDGAR submissions API.
    Returns list of filing dicts.
    """
    # Pad CIK to 10 digits
    cik_padded = cik.zfill(10)
    url = f"{BASE_URL}/submissions/CIK{cik_padded}.json"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()

        filings = data.get("filings", {}).get("recent", {})
        forms       = filings.get("form", [])
        dates       = filings.get("filingDate", [])
        accessions  = filings.get("accessionNumber", [])
        descriptions= filings.get("primaryDocument", [])
        items_list  = filings.get("items", [])

        results = []
        for i, form in enumerate(forms):
            if form not in ("8-K", "8-K/A"):
                continue
            filing_date = dates[i] if i < len(dates) else ""
            if filing_date < start_date:
                continue

            acc     = accessions[i] if i < len(accessions) else ""
            primary = descriptions[i] if i < len(descriptions) else ""
            items   = items_list[i] if i < len(items_list) else ""

            # Build filing URL
            acc_clean = acc.replace("-", "")
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{acc_clean}/{primary}"
            )
            index_url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?action=getcompany&CIK={cik_padded}"
                f"&type=8-K&dateb=&owner=include&count=10"
            )

            results.append({
                "Ticker":      ticker,
                "Form":        form,
                "Filed":       filing_date,
                "Items":       items,
                "Accession":   acc,
                "URL":         f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/",
                "Primary Doc": primary,
            })

        return results

    except Exception as e:
        print(f"    ✗ {ticker} ({cik}): {e}")
        return []


def classify_signal(items_str: str) -> tuple:
    """
    Given the items string from an 8-K, determine signal level.
    Returns (signal_level, item_descriptions)
    """
    if not items_str:
        return "standard", []

    # Items are comma-separated like "1.01,5.02,9.01"
    item_codes = [i.strip() for i in str(items_str).split(",")]
    descriptions = []
    has_high_signal = False

    for code in item_codes:
        if code in HIGH_SIGNAL_ITEMS:
            descriptions.append(f"★ {code}: {HIGH_SIGNAL_ITEMS[code]}")
            has_high_signal = True
        elif code in STANDARD_ITEMS:
            descriptions.append(f"  {code}: {STANDARD_ITEMS[code]}")
        elif code:
            descriptions.append(f"  {code}: Item {code}")

    level = "HIGH" if has_high_signal else "standard"
    return level, descriptions


# ── SCAN ─────────────────────────────────────────────────────────────────────

def scan_8k(watchlist: dict, lookback_days: int) -> pd.DataFrame:
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    print(f"\n{'─'*65}")
    print(f"  Scanning EDGAR for 8-K filings...")
    print(f"  Tickers  : {len(watchlist)}")
    print(f"  Lookback : {lookback_days} days (since {start_date})")
    print(f"{'─'*65}")

    all_rows = []
    for ticker, cik in watchlist.items():
        print(f"  {ticker:<6}", end="  ")
        rows = get_company_filings(cik, ticker, start_date)
        print(f"{len(rows)} filing(s)")
        all_rows.extend(rows)
        time.sleep(0.12)   # EDGAR rate limit: ~10 req/sec

    print(f"\n  Total 8-Ks found: {len(all_rows)}")
    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


# ── OUTPUT ────────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame):
    print(f"\n{'═'*65}")
    print(f"  EVERSTAR — 8-K MATERIAL EVENT MONITOR")
    print(f"  Generated : {datetime.now().strftime('%A, %B %d %Y  %H:%M')}")
    print(f"  Filings   : {len(df)}")
    print(f"{'═'*65}")

    if df.empty:
        print("  No 8-K filings found in this period.")
        return

    # Classify all filings
    df = df.copy()
    df["Signal"]       = df["Items"].apply(lambda x: classify_signal(x)[0])
    df["Descriptions"] = df["Items"].apply(lambda x: classify_signal(x)[1])

    # ── High signal filings first ──
    high = df[df["Signal"] == "HIGH"].sort_values("Filed", ascending=False)

    if not high.empty:
        print(f"\n  ── HIGH SIGNAL FILINGS ({len(high)}) {'─'*35}")
        for _, row in high.iterrows():
            print(f"\n  ★ {row['Ticker']}  |  {row['Form']}  |  Filed: {row['Filed']}")
            for desc in row["Descriptions"]:
                print(f"    {desc}")
            print(f"    → {row['URL']}")
    else:
        print(f"\n  ✓ No high-signal 8-K items in this period.")

    # ── All filings by ticker ──
    print(f"\n  ── ALL FILINGS {'─'*50}")
    for ticker, group in df.groupby("Ticker"):
        print(f"\n  {ticker} ({len(group)} filings)")
        for _, row in group.sort_values("Filed", ascending=False).iterrows():
            signal_marker = "★" if row["Signal"] == "HIGH" else "·"
            items_short = str(row["Items"])[:60] if row["Items"] else "—"
            print(f"    {signal_marker} {row['Filed']}  {row['Form']:<6}  "
                  f"Items: {items_short}")
            print(f"      {row['URL']}")

    # ── Stats ──
    print(f"\n{'═'*65}")
    print(f"  SUMMARY")
    print(f"{'─'*65}")
    print(f"  Total filings    : {len(df)}")
    print(f"  High signal      : {len(high)}")
    print(f"  Standard         : {len(df) - len(high)}")
    print(f"  Tickers with 8-K : {df['Ticker'].nunique()}")

    # Most active filers
    top_filers = df["Ticker"].value_counts().head(10)
    print(f"\n  Most active filers:")
    for ticker, count in top_filers.items():
        print(f"    {ticker:<6} {count} filing(s)")
    print(f"{'═'*65}\n")


def export(df: pd.DataFrame, path: str = "eightk_results.csv"):
    if df.empty:
        return
    df_export = df.copy()
    df_export["Signal"] = df["Items"].apply(lambda x: classify_signal(x)[0])
    out_cols = ["Ticker","Form","Filed","Items","Signal","URL"]
    df_export[out_cols].sort_values(
        ["Signal","Filed"], ascending=[True, False]
    ).to_csv(path, index=False)
    print(f"  Exported → {path}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'─'*65}")
    print(f"  8-K Monitor — Everstar Alternative Data")
    print(f"  Source: SEC EDGAR  |  Free  |  ~4 business day lag")
    print(f"{'─'*65}")

    df = scan_8k(WATCHLIST, LOOKBACK_DAYS)

    if df.empty:
        print("\n  No data collected.")
        return

    # Add signal classification
    df["Signal"]       = df["Items"].apply(lambda x: classify_signal(x)[0])
    df["Descriptions"] = df["Items"].apply(lambda x: classify_signal(x)[1])

    print_summary(df)
    export(df)

    # Colab display
    try:
        from IPython.display import display
        high = df[df["Signal"] == "HIGH"].sort_values("Filed", ascending=False)
        display_df = high if not high.empty else df.sort_values("Filed", ascending=False)
        display(display_df[["Ticker","Form","Filed","Items","Signal","URL"]
                           ].reset_index(drop=True))
    except ImportError:
        pass


if __name__ == "__main__":
    main()
