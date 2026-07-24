
# ===== CELL 0 =====
!pip install edgartools pandas

# ===== CELL 1 =====
"""
Everstar — Form 4 Insider Transaction Scanner v3
=================================================
Fixed parser for current edgartools API.
Uses Form4.common_stock_purchases, common_stock_sales, and to_dataframe.

Usage (Colab):
    !pip install edgartools pandas
    # Set YOUR_EMAIL below then run
"""

import time
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from datetime import datetime, timedelta
from edgar import Company, set_identity

# ── CONFIG ────────────────────────────────────────────────────────────────────

YOUR_NAME  = "Ryan Chrostowski"
YOUR_EMAIL = "ryan-ski@comcast.net"   # ← change this

TICKERS = [
    # Industrials & Transport
    "GXO", "SAIA", "ARCB", "WERN", "CHRW", "HUBG", "MATX",
    # Energy
    "AMR", "SXC", "SM", "AROC", "NOG", "TALO", "KNTK",
    # Materials & Metals
    "CLF", "CMC", "STLD", "KALU", "CENX",
    # Agriculture & Food
    "INGR", "CALM", "VITL", "ANDE",
    # Regional Banks
    "CATY", "FFIN", "CVBF", "HOPE", "BANR", "HOMB", "SFBS",
    # Consumer & Retail
    "PRGO", "CENT", "DXLG", "BOOT", "GIII", "OXM",
    # Healthcare
    "SUPN", "HALO", "PCRX", "PAHC", "AMSF",
    # Technology / Semiconductors
    "MTSI", "DIOD", "FORM", "PLAB", "COHU", "ICHR",
    # REITs
    "NXRT", "ELME", "GOOD", "APLE",
    # Specialty
    "POWL", "GRC", "PUMP", "WTTR", "NINE",
]

LOOKBACK_DAYS    = 14
MIN_PURCHASE_USD = 100_000
MIN_SALE_USD     = 500_000

SENIOR_ROLES = ["CEO", "CFO", "COO", "President", "Director",
                "Chairman", "CTO", "EVP", "SVP", "10%", "General Counsel"]

# ── HELPERS ───────────────────────────────────────────────────────────────────

def is_senior(title: str) -> bool:
    if not title:
        return False
    t = str(title).upper()
    return any(r.upper() in t for r in SENIOR_ROLES)


def safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def safe_int(val, default=0):
    try:
        return int(float(val)) if val is not None else default
    except (TypeError, ValueError):
        return default


def get_owner_info(f4_obj):
    """Extract owner name and title from reporting_owners."""
    name, title = "Unknown", ""
    try:
        ro = f4_obj.reporting_owners
        if ro is None:
            return name, title

        # reporting_owners is a ReportingOwners object with .owners list
        owners_list = getattr(ro, "owners", None)
        if not owners_list:
            # maybe it IS the list
            owners_list = [ro]

        owner = owners_list[0]

        # Name
        name = str(getattr(owner, "name", None) or "Unknown").strip()

        # Title — try several attribute names
        title = (
            getattr(owner, "position",      None) or
            getattr(owner, "officer_title", None) or
            getattr(owner, "title",         None) or
            getattr(owner, "relationship",  None) or
            ""
        )
        title = str(title).strip()

    except Exception:
        pass
    return name, title


def parse_form4_obj(f4_obj, ticker, filing_date) -> list:
    """
    Parse using the confirmed edgartools Form4 API:
      - f4_obj.common_stock_purchases  → buys
      - f4_obj.common_stock_sales      → sells
      - f4_obj.to_dataframe()          → full table fallback
    """
    rows = []
    owner_name, owner_title = get_owner_info(f4_obj)

    def make_row(code, shares, price, date=None, notes=""):
        usd = safe_float(shares) * safe_float(price)
        return {
            "Ticker":      ticker,
            "Insider":     owner_name,
            "Title":       owner_title,
            "Senior":      is_senior(owner_title),
            "Date":        str(date or filing_date),
            "Code":        str(code).strip(),
            "Type":        {"P": "Open Market Purchase",
                            "S": "Open Market Sale",
                            "A": "Grant / Award",
                            "M": "Option Exercise",
                            "F": "Tax Withholding"}.get(str(code).strip(), str(code)),
            "Shares":      safe_int(shares),
            "Price":       round(safe_float(price), 2),
            "Value ($)":   round(usd),
            "Filing Date": str(filing_date),
            "10b5-1":      "10b5-1" in str(notes).lower(),
        }

    # ── Method 1: common_stock_purchases / common_stock_sales ──
    parsed_via_method1 = False
    try:
        purchases = f4_obj.common_stock_purchases or []
        for tx in purchases:
            try:
                rows.append(make_row(
                    code   = getattr(tx, "transaction_code", "P") or "P",
                    shares = getattr(tx, "shares", None) or getattr(tx, "transaction_shares", 0),
                    price  = getattr(tx, "price",  None) or getattr(tx, "transaction_price", 0),
                    date   = getattr(tx, "date",   None) or getattr(tx, "transaction_date", filing_date),
                    notes  = str(getattr(tx, "footnotes", "") or ""),
                ))
                parsed_via_method1 = True
            except Exception:
                continue

        sales = f4_obj.common_stock_sales or []
        for tx in sales:
            try:
                rows.append(make_row(
                    code   = getattr(tx, "transaction_code", "S") or "S",
                    shares = getattr(tx, "shares", None) or getattr(tx, "transaction_shares", 0),
                    price  = getattr(tx, "price",  None) or getattr(tx, "transaction_price", 0),
                    date   = getattr(tx, "date",   None) or getattr(tx, "transaction_date", filing_date),
                    notes  = str(getattr(tx, "footnotes", "") or ""),
                ))
                parsed_via_method1 = True
            except Exception:
                continue
    except Exception:
        pass

    if parsed_via_method1:
        return rows

    # ── Method 2: to_dataframe() ──
    try:
        df = f4_obj.to_dataframe()
        if df is not None and not df.empty:
            # Normalize column names to lowercase
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]

            # Map common column name variants
            col = lambda *names: next((n for n in names if n in df.columns), None)

            code_col   = col("transaction_code", "code", "transactioncode")
            shares_col = col("transaction_shares", "shares", "amount")
            price_col  = col("transaction_price_per_share", "price", "transactionpricepershare")
            date_col   = col("transaction_date", "date", "transactiondate")
            notes_col  = col("footnotes", "notes", "transaction_footnotes")

            for _, r in df.iterrows():
                try:
                    rows.append(make_row(
                        code   = r.get(code_col,   "") if code_col   else "",
                        shares = r.get(shares_col, 0)  if shares_col else 0,
                        price  = r.get(price_col,  0)  if price_col  else 0,
                        date   = r.get(date_col,   filing_date) if date_col else filing_date,
                        notes  = str(r.get(notes_col, "")) if notes_col else "",
                    ))
                except Exception:
                    continue
    except Exception:
        pass

    # ── Method 3: non_derivative_table ──
    if not rows:
        try:
            table = f4_obj.non_derivative_table
            if table is not None:
                df = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
                if not df.empty:
                    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
                    for _, r in df.iterrows():
                        try:
                            rows.append(make_row(
                                code   = r.get("transaction_code", r.get("code", "")),
                                shares = r.get("transaction_shares", r.get("shares", 0)),
                                price  = r.get("transaction_price_per_share", r.get("price", 0)),
                                date   = r.get("transaction_date", r.get("date", filing_date)),
                            ))
                        except Exception:
                            continue
        except Exception:
            pass

    return rows


def scan_ticker(ticker: str, start_date: str) -> list:
    rows = []
    try:
        company = Company(ticker)
        filings = company.get_filings(form="4")
        recent  = [f for f in filings if str(f.filing_date) >= start_date]

        if not recent:
            print(f"  {ticker:<6}  no filings in window")
            return []

        print(f"  {ticker:<6}  {len(recent)} filing(s)", end="")
        parsed_count = 0
        for filing in recent:
            try:
                f4_obj = filing.obj()
                if f4_obj is not None:
                    parsed = parse_form4_obj(f4_obj, ticker, filing.filing_date)
                    rows.extend(parsed)
                    parsed_count += len(parsed)
            except Exception as e:
                pass
            time.sleep(0.12)

        print(f"  →  {parsed_count} transactions parsed")

    except Exception as e:
        err = str(e)
        if "not found" in err.lower():
            print(f"  {ticker:<6}  SKIPPED — not found (delisted?)")
        else:
            print(f"  {ticker:<6}  ERROR — {err[:80]}")
    return rows


def flag_signals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["Signal"] = ""

    buy_mask = (
        (df["Code"] == "P") &
        (df["Senior"] == True) &
        (df["Value ($)"] >= MIN_PURCHASE_USD) &
        (df["10b5-1"] == False)
    )
    df.loc[buy_mask, "Signal"] = "★ BUY SIGNAL"

    sale_mask = (
        (df["Code"] == "S") &
        (df["Senior"] == True) &
        (df["Value ($)"] >= MIN_SALE_USD) &
        (df["10b5-1"] == False)
    )
    df.loc[sale_mask, "Signal"] = "⚠ LARGE SALE"

    buys = df[df["Signal"] == "★ BUY SIGNAL"].copy()
    if not buys.empty:
        buys["Week"]  = pd.to_datetime(buys["Date"], errors="coerce").dt.isocalendar().week
        cluster       = buys.groupby(["Ticker", "Week"]).size()
        cluster_tkrs  = cluster[cluster >= 2].index.get_level_values("Ticker").unique()
        mask = df["Ticker"].isin(cluster_tkrs) & (df["Signal"] == "★ BUY SIGNAL")
        df.loc[mask, "Signal"] = "★★ CLUSTER BUY"

    return df


def print_summary(df: pd.DataFrame, start_date: str):
    print(f"\n{'═'*72}")
    print(f"  EVERSTAR — FORM 4 INSIDER SCANNER")
    print(f"  Period : {start_date} → {datetime.now().strftime('%Y-%m-%d')}")
    print(f"  Tickers: {len(TICKERS)}  |  Transactions: {len(df)}")
    print(f"{'═'*72}")

    if df.empty:
        print("  No transactions parsed.")
        print("  Try running the debug cell — paste output back to Claude.")
        print(f"{'═'*72}\n")
        return

    flagged = df[df["Signal"] != ""].sort_values("Value ($)", ascending=False)

    if flagged.empty:
        print("\n  ✓ No signals flagged this period.")
    else:
        print(f"\n  ── FLAGGED {'─'*60}")
        for _, r in flagged.iterrows():
            print(
                f"\n  {r['Signal']}"
                f"\n  {r['Ticker']}  |  {r['Insider']}  ({r['Title']})"
                f"\n  {r['Type']}  —  {r['Shares']:,} shares @ ${r['Price']:.2f}"
                f"  =  ${r['Value ($)']:,.0f}"
                f"\n  Transaction: {r['Date']}  |  Filed: {r['Filing Date']}"
                + ("  |  ⚑ 10b5-1" if r["10b5-1"] else "")
            )

    print(f"\n  ── ALL TRANSACTIONS {'─'*52}")
    for ticker, grp in df.groupby("Ticker"):
        print(f"\n  ── {ticker} {'─'*(60-len(ticker))}")
        for _, r in grp.sort_values("Date", ascending=False).iterrows():
            flag = f"  ← {r['Signal']}" if r["Signal"] else ""
            print(
                f"  {r['Date']}  {r['Code']}  {r['Type']:<25}"
                f"  {r['Shares']:>10,} sh @ ${r['Price']:>8.2f}"
                f"  = ${r['Value ($)']:>12,.0f}"
                f"  {str(r['Insider'])[:28]}{flag}"
            )

    print(f"\n{'═'*72}  STATS")
    for code, grp in df.groupby("Code"):
        lbl = {"P":"Open Market Purchase","S":"Open Market Sale",
               "A":"Grant/Award","M":"Option Exercise","F":"Tax Withholding"}.get(code, code)
        print(f"  {code}  {lbl:<28}  {len(grp):>4} tx  ${grp['Value ($)'].sum():>14,.0f}")

    n_buy     = len(df[df["Signal"].str.contains("BUY", na=False)])
    n_cluster = len(df[df["Signal"] == "★★ CLUSTER BUY"]["Ticker"].unique())
    n_sale    = len(df[df["Signal"] == "⚠ LARGE SALE"])
    print(f"\n  Buy signals:      {n_buy}")
    print(f"  Cluster tickers:  {n_cluster}")
    print(f"  Large sale flags: {n_sale}")
    print(f"{'═'*72}\n")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    set_identity(f"{YOUR_NAME} {YOUR_EMAIL}")
    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    print(f"\n{'─'*72}")
    print(f"  Scanning {len(TICKERS)} tickers for Form 4s since {start_date}")
    print(f"  Flagging: Code P ≥ ${MIN_PURCHASE_USD:,} by senior insiders (no 10b5-1)")
    print(f"{'─'*72}")

    all_rows = []
    for ticker in TICKERS:
        all_rows.extend(scan_ticker(ticker, start_date))
        time.sleep(0.1)

    if not all_rows:
        print("\n  Still no transactions parsed — run this debug cell:\n")
        print("  from edgar import Company, set_identity")
        print(f"  set_identity('{YOUR_NAME} {YOUR_EMAIL}')")
        print("  c = Company('WERN')")
        print("  f = c.get_filings(form='4')[0]")
        print("  f4 = f.obj()")
        print("  print(f4.common_stock_purchases)")
        print("  print(f4.common_stock_sales)")
        print("  print(f4.to_dataframe())")
        return

    df = pd.DataFrame(all_rows)
    df = flag_signals(df)
    print_summary(df, start_date)

    df.to_csv("form4_results.csv", index=False)
    print("  Exported → form4_results.csv")

    try:
        from IPython.display import display
        flagged = df[df["Signal"] != ""].sort_values("Value ($)", ascending=False)
        target  = flagged if not flagged.empty else df
        display(target[["Ticker","Date","Insider","Title","Code",
                         "Shares","Price","Value ($)","Signal"]
                       ].reset_index(drop=True))
    except ImportError:
        pass


if __name__ == "__main__":
    main()


# ===== CELL 2 =====
from edgar import Company, set_identity
set_identity("Everstar Research your_email@example.com")

c = Company("CMC")
filings = c.get_filings(form="4")
f = filings[0]
f4 = f.obj()

print("reporting_owners type:", type(f4.reporting_owners))
print("reporting_owners value:", f4.reporting_owners)

# If it's a list, inspect first element
owners = f4.reporting_owners
if owners:
    o = owners[0] if isinstance(owners, list) else owners
    print("\nowner type:", type(o))
    print("owner dir:", dir(o))
    print("owner vars:", vars(o) if hasattr(o, '__dict__') else "no __dict__")