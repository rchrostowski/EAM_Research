
# ===== CELL 0 =====
"""
Everstar — WARN Act Layoff Scanner
====================================
Scrapes LayoffAlert.org for WARN Act filings across your watchlist.
Flags any company in your portfolio or watchlist that has filed a
mass layoff or plant closure notice — giving you 60 days advance warning.

Source: layoffalert.org (aggregates official state labor dept filings)
Coverage: 49 states, updated daily

Usage (Colab):
    !pip install requests beautifulsoup4 pandas
    # No API key needed — fully public data
"""

import warnings
warnings.filterwarnings("ignore")

import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────

# Format: "TICKER": ["Legal name variant 1", "Legal name variant 2", ...]
# Include subsidiaries — large companies often file under sub entity names
# Cross-check 10-K Exhibit 21 for full subsidiary lists on key holdings

WATCHLIST = {
    # ── Industrials & Transport ──────────────────────────────────────────
    "CMC":   ["Commercial Metals", "CMC Steel"],
    "NUE":   ["Nucor"],
    "STLD":  ["Steel Dynamics"],
    "CLF":   ["Cleveland-Cliffs", "Cliffs Natural"],
    "X":     ["United States Steel", "U.S. Steel"],
    "GXO":   ["GXO Logistics", "GXO Warehouse"],
    "WERN":  ["Werner Enterprises", "Werner"],
    "SAIA":  ["Saia"],
    "UNP":   ["Union Pacific"],
    "NSC":   ["Norfolk Southern"],
    "CSX":   ["CSX Transportation", "CSX"],
    "DE":    ["Deere", "John Deere"],
    "CAT":   ["Caterpillar"],
    "EMR":   ["Emerson Electric", "Emerson"],
    "ETN":   ["Eaton"],
    "PWR":   ["Quanta Services"],

    # ── Energy ──────────────────────────────────────────────────────────
    "XOM":   ["ExxonMobil", "Exxon Mobil", "Exxon"],
    "CVX":   ["Chevron"],
    "COP":   ["ConocoPhillips"],
    "SLB":   ["Schlumberger", "SLB"],
    "HAL":   ["Halliburton"],
    "BKR":   ["Baker Hughes"],
    "MPC":   ["Marathon Petroleum", "Marathon"],
    "VLO":   ["Valero"],
    "PSX":   ["Phillips 66"],
    "OXY":   ["Occidental Petroleum", "Occidental"],

    # ── Materials ────────────────────────────────────────────────────────
    "DOW":   ["Dow Chemical", "Dow Inc"],
    "LYB":   ["LyondellBasell"],
    "CE":    ["Celanese"],
    "PPG":   ["PPG Industries"],
    "APD":   ["Air Products"],
    "ECL":   ["Ecolab"],
    "NEM":   ["Newmont", "Newmont Mining"],
    "FCX":   ["Freeport-McMoRan", "Freeport"],

    # ── Consumer & Retail ────────────────────────────────────────────────
    "WMT":   ["Walmart", "Wal-Mart"],
    "TGT":   ["Target"],
    "COST":  ["Costco"],
    "KR":    ["Kroger"],
    "WBA":   ["Walgreens", "Walgreen"],
    "CVS":   ["CVS Health", "CVS Pharmacy", "CVS"],
    "HD":    ["Home Depot"],
    "LOW":   ["Lowe's", "Lowes"],
    "MCD":   ["McDonald's"],
    "SBUX":  ["Starbucks"],
    "YUM":   ["Yum! Brands", "Yum Brands", "KFC", "Pizza Hut", "Taco Bell"],
    "NKE":   ["Nike"],
    "GPS":   ["Gap", "Old Navy", "Banana Republic"],
    "M":     ["Macy's", "Macy's Retail"],
    "KSS":   ["Kohl's"],

    # ── Technology ───────────────────────────────────────────────────────
    "MSFT":  ["Microsoft"],
    "GOOGL": ["Google", "Alphabet"],
    "META":  ["Meta Platforms", "Facebook"],
    "AMZN":  ["Amazon", "Amazon.com"],
    "NVDA":  ["Nvidia", "NVIDIA"],
    "INTC":  ["Intel"],
    "AMD":   ["Advanced Micro Devices", "AMD"],
    "IBM":   ["International Business Machines", "IBM"],
    "ORCL":  ["Oracle America", "Oracle"],
    "SAP":   ["SAP"],
    "CRM":   ["Salesforce"],
    "ADBE":  ["Adobe"],
    "CSCO":  ["Cisco"],
    "HPQ":   ["HP Inc", "Hewlett Packard"],
    "HPE":   ["Hewlett Packard Enterprise"],
    "DELL":  ["Dell Technologies", "Dell"],

    # ── Financials & Banks ───────────────────────────────────────────────
    "JPM":   ["JPMorgan", "JP Morgan", "Chase"],
    "BAC":   ["Bank of America"],
    "WFC":   ["Wells Fargo"],
    "C":     ["Citibank", "Citigroup", "Citigroup Technology"],
    "GS":    ["Goldman Sachs", "Goldman"],
    "MS":    ["Morgan Stanley"],
    "AXP":   ["American Express"],
    "COF":   ["Capital One"],
    "USB":   ["U.S. Bank", "US Bancorp"],
    "PNC":   ["PNC Bank", "PNC Financial"],

    # ── Healthcare & Pharma ──────────────────────────────────────────────
    "JNJ":   ["Johnson & Johnson", "J&J"],
    "PFE":   ["Pfizer"],
    "MRK":   ["Merck"],
    "ABBV":  ["AbbVie"],
    "BMY":   ["Bristol Myers Squibb", "Bristol-Myers"],
    "LLY":   ["Eli Lilly", "Lilly"],
    "AMGN":  ["Amgen"],
    "GILD":  ["Gilead Sciences", "Gilead"],
    "BIIB":  ["Biogen"],
    "REGN":  ["Regeneron"],
    "UNH":   ["UnitedHealth", "United Health", "Optum"],
    "CVS":   ["CVS Health", "Aetna"],
    "PRGO":  ["Perrigo"],
    "HALO":  ["Halozyme"],
    "NVO":   ["Novo Nordisk"],

    # ── Media & Telecom ──────────────────────────────────────────────────
    "VZ":    ["Verizon", "Verizon Corp"],
    "T":     ["AT&T"],
    "CMCSA": ["Comcast"],
    "PARA":  ["Paramount Global", "Paramount", "ViacomCBS"],
    "WBD":   ["Warner Bros", "Warner Brothers", "Discovery"],
    "DIS":   ["Disney", "Walt Disney"],
    "NFLX":  ["Netflix"],
    "SPOT":  ["Spotify"],

    # ── Mid-cap industrials (high insider signal value) ──────────────────
    "POWL":  ["Powell Industries", "Powell"],
    "INGR":  ["Ingredion"],
    "CALM":  ["Cal-Maine Foods", "Cal-Maine"],
    "BOOT":  ["Boot Barn"],
    "COHU":  ["Cohu"],
    "WTTR":  ["Select Water Solutions", "WTTR"],
    "AROC":  ["Archrock"],
    "NOG":   ["Northern Oil and Gas", "Northern Oil"],
    "MTSI":  ["MACOM Technology", "MACOM"],
    "FORM":  ["FormFactor"],
}

LOOKBACK_DAYS = 90

STATES = [
    "NY", "NJ", "TX", "PA", "OH", "CA", "IL", "FL",
    "WA", "VA", "GA", "NC", "MI", "MA", "MO", "AZ",
    "IN", "MD", "WI", "KY", "OK", "IA", "MN", "CO",
    "TN", "SC", "AL", "OR", "WV", "LA",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

BASE_URL = "https://layoffalert.org"

# ── SCRAPER ───────────────────────────────────────────────────────────────────

def scrape_state(state_code: str) -> list:
    url = f"{BASE_URL}/state/{state_code}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        for table in soup.find_all("table"):
            header_row = table.find("tr")
            if not header_row:
                continue
            header_text = header_row.get_text().lower()
            if "company" not in header_text:
                continue
            for tr in table.find_all("tr")[1:]:
                cols = tr.find_all(["td", "th"])
                if len(cols) < 3:
                    continue
                try:
                    rows.append({
                        "State":          state_code,
                        "Company":        cols[0].get_text(strip=True),
                        "Location":       cols[1].get_text(strip=True) if len(cols) > 1 else "",
                        "Effective Date": cols[2].get_text(strip=True) if len(cols) > 2 else "",
                        "Employees":      cols[3].get_text(strip=True) if len(cols) > 3 else "",
                        "Type":           cols[4].get_text(strip=True) if len(cols) > 4 else "",
                    })
                except Exception:
                    continue
        return rows
    except Exception as e:
        print(f"    ✗ {state_code}: {e}")
        return []


def scrape_homepage() -> list:
    try:
        r = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        for table in soup.find_all("table"):
            header_row = table.find("tr")
            if not header_row:
                continue
            if "company" not in header_row.get_text().lower():
                continue
            for tr in table.find_all("tr")[1:]:
                cols = tr.find_all(["td", "th"])
                if len(cols) < 3:
                    continue
                try:
                    rows.append({
                        "State":          "LATEST",
                        "Company":        cols[0].get_text(strip=True),
                        "Location":       cols[1].get_text(strip=True) if len(cols) > 1 else "",
                        "Effective Date": cols[2].get_text(strip=True) if len(cols) > 2 else "",
                        "Employees":      cols[3].get_text(strip=True) if len(cols) > 3 else "",
                        "Type":           cols[4].get_text(strip=True) if len(cols) > 4 else "",
                    })
                except Exception:
                    continue
        return rows
    except Exception as e:
        print(f"    ✗ Homepage: {e}")
        return []


def parse_date(date_str: str):
    for fmt in ["%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def match_ticker(company_name: str, watchlist: dict):
    company_lower = company_name.lower()
    for ticker, aliases in watchlist.items():
        for alias in aliases:
            if alias.lower() in company_lower:
                return ticker
    return None


# ── SCAN ─────────────────────────────────────────────────────────────────────

def scan_warn(watchlist, states, lookback_days):
    cutoff  = datetime.now() - timedelta(days=lookback_days)
    all_rows = []

    print(f"\n{'─'*65}")
    print(f"  Scanning for WARN Act filings...")
    print(f"  Watchlist: {len(watchlist)} tickers  |  States: {len(states)}")
    print(f"  Lookback : {lookback_days} days (since {cutoff.strftime('%Y-%m-%d')})")
    print(f"{'─'*65}")

    print(f"  Scraping homepage (latest cross-state filings)...", end="")
    hp = scrape_homepage()
    all_rows.extend(hp)
    print(f" {len(hp)} filings")
    time.sleep(1.5)

    for state in states:
        print(f"  {state}...", end="  ")
        rows = scrape_state(state)
        all_rows.extend(rows)
        print(f"{len(rows)} filings")
        time.sleep(0.8)

    print(f"\n  Total collected: {len(all_rows)} filings")

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["Company", "Effective Date", "State"])
    df["Parsed Date"] = df["Effective Date"].apply(parse_date)
    df = df[df["Parsed Date"].notna()]
    df = df[df["Parsed Date"] >= cutoff].copy()
    df["Ticker"] = df["Company"].apply(lambda c: match_ticker(c, watchlist))

    return df


# ── OUTPUT ────────────────────────────────────────────────────────────────────

def print_summary(df, watchlist):
    print(f"\n{'═'*65}")
    print(f"  EVERSTAR — WARN ACT SCANNER")
    print(f"  Generated : {datetime.now().strftime('%A, %B %d %Y  %H:%M')}")
    print(f"  Tickers monitored: {len(watchlist)}")
    print(f"{'═'*65}")

    hits = df[df["Ticker"].notna()].sort_values("Parsed Date", ascending=False)

    if hits.empty:
        print(f"\n  ✓ No WARN Act filings found for any watchlist ticker.")
    else:
        print(f"\n  ⚠  WATCHLIST HITS — {len(hits)} filing(s)\n")
        for _, row in hits.iterrows():
            days_out = (row["Parsed Date"] - datetime.now()).days
            timing = (f"{days_out} days until effective"
                      if days_out > 0 else f"effective {abs(days_out)} days ago")
            print(f"  {'─'*60}")
            print(f"  ★ {row['Ticker']}  |  {row['Company']}")
            print(f"  Type      : {row['Type'].upper()}")
            print(f"  Location  : {row['Location']}  ({row['State']})")
            print(f"  Effective : {row['Effective Date']}  ({timing})")
            print(f"  Employees : {row['Employees'] or 'not disclosed'}")

    print(f"\n{'─'*65}")
    print(f"  TOP 20 LARGEST RECENT FILINGS (all companies)")
    print(f"{'─'*65}")

    df2 = df.copy()
    df2["Emp_n"] = pd.to_numeric(
        df2["Employees"].str.replace(",", ""), errors="coerce"
    )
    top = df2[df2["Emp_n"] > 0].sort_values("Emp_n", ascending=False).head(20)

    if not top.empty:
        print(f"  {'Company':<38} {'St':<4} {'Employees':>10}  {'Effective':<14}  Ticker")
        print(f"  {'─'*38} {'─'*4} {'─'*10}  {'─'*14}  {'─'*6}")
        for _, row in top.iterrows():
            t = f"[{row['Ticker']}]" if pd.notna(row.get("Ticker")) else ""
            print(
                f"  {row['Company'][:36]:<38} "
                f"{row['State']:<4} "
                f"{int(row['Emp_n']):>10,}  "
                f"{row['Effective Date']:<14}  {t}"
            )

    print(f"\n{'═'*65}")
    total_emp = pd.to_numeric(
        df["Employees"].str.replace(",", ""), errors="coerce"
    ).sum()
    print(f"  Filings in window : {len(df):,}")
    print(f"  Watchlist hits    : {len(hits)}")
    if not pd.isna(total_emp):
        print(f"  Employees at risk : {int(total_emp):,}")
    for t, c in df["Type"].value_counts().items():
        if t:
            print(f"  {t.capitalize():<16}: {c:,} filings")
    print(f"{'═'*65}\n")


def main():
    print(f"\n{'─'*65}")
    print(f"  WARN Act Scanner — Everstar Alternative Data")
    print(f"  Source: layoffalert.org  |  49 states  |  updated daily")
    print(f"{'─'*65}")

    df = scan_warn(WATCHLIST, STATES, LOOKBACK_DAYS)

    if df.empty:
        print("\n  No data collected.")
        return

    print_summary(df, WATCHLIST)

    df.to_csv("warn_results.csv", index=False)
    print(f"  Exported → warn_results.csv")

    try:
        from IPython.display import display
        hits = df[df["Ticker"].notna()]
        display_df = hits if not hits.empty else df.head(50)
        display(display_df[["Ticker","Company","State","Location",
                             "Effective Date","Employees","Type"]
                           ].reset_index(drop=True))
    except ImportError:
        pass


if __name__ == "__main__":
    main()
