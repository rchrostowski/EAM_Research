import io
import os
import time
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from fredapi import Fred

try:
    from edgar import Company, set_identity
    EDGARTOOLS_AVAILABLE = True
except Exception:
    EDGARTOOLS_AVAILABLE = False

st.set_page_config(page_title="Everstar Alternative Data Dashboard", page_icon="📊", layout="wide")

# ----------------------------- CONFIG ---------------------------------
FRED_SERIES = {
    "Rail Carloads (Total)": ("RAILFRTCARLOADSD11", "Supply Chain & Trade", "neutral"),
    "Rail Intermodal Units": ("RAILFRTINTERMODAL", "Supply Chain & Trade", "neutral"),
    "Freight Transport Index": ("TSIFRGHT", "Supply Chain & Trade", "neutral"),
    "Industrial Production": ("INDPRO", "Industrial Activity", "neutral"),
    "Capacity Utilization (Mfg)": ("CAPUTLB00004SQ", "Industrial Activity", "neutral"),
    "Durable Goods New Orders": ("AMTMNO", "Industrial Activity", "neutral"),
    "Mfg New Orders": ("MNFCTRSMSA", "Industrial Activity", "neutral"),
    "Retail Sales ex Food & Gas": ("RSXFS", "Consumer & Retail", "neutral"),
    "Consumer Sentiment (UMich)": ("UMCSENT", "Consumer & Retail", "neutral"),
    "Real Disposable Income": ("DSPIC96", "Consumer & Retail", "neutral"),
    "WTI Crude Oil (Daily)": ("DCOILWTICO", "Energy", "neutral"),
    "Henry Hub Natural Gas": ("DHHNGSP", "Energy", "neutral"),
    "Initial Jobless Claims": ("ICSA", "Labor Market", "inverted"),
    "Continuing Claims": ("CCSA", "Labor Market", "inverted"),
    "Job Openings (JOLTS)": ("JTSJOL", "Labor Market", "neutral"),
    "HY Credit Spread": ("BAMLH0A0HYM2", "Credit & Financial Conditions", "inverted"),
    "STL Financial Stress Index": ("STLFSI4", "Credit & Financial Conditions", "inverted"),
    "NY Fed Weekly Econ Index": ("WEI", "Composite / Nowcast", "neutral"),
}

CONSUMER_SERIES = {
    "Personal Savings Rate": ("PSAVERT", "neutral"),
    "Total Consumer Credit ($B)": ("TOTALSL", "inverted"),
    "Revolving Credit / Cards ($B)": ("REVOLSL", "inverted"),
    "Credit Card Delinquency Rate": ("DRCCLACBS", "inverted"),
}

RETAIL_URL = "https://www.census.gov/retail/mrts/www/mrtssales92-present.xlsx"
MONTH_COLS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]

SENIOR_ROLES = ["CEO", "CFO", "COO", "President", "Director", "Chairman", "CTO", "EVP", "SVP", "10%", "General Counsel"]

WARN_ALIASES = {
    "CMC": ["Commercial Metals", "CMC Steel"], "NUE": ["Nucor"], "STLD": ["Steel Dynamics"],
    "CLF": ["Cleveland-Cliffs", "Cliffs Natural"], "X": ["United States Steel", "U.S. Steel"],
    "GXO": ["GXO Logistics", "GXO Warehouse"], "WERN": ["Werner Enterprises", "Werner"],
    "SAIA": ["Saia"], "UNP": ["Union Pacific"], "NSC": ["Norfolk Southern"], "CSX": ["CSX Transportation", "CSX"],
    "DE": ["Deere", "John Deere"], "CAT": ["Caterpillar"], "XOM": ["ExxonMobil", "Exxon Mobil", "Exxon"],
    "CVX": ["Chevron"], "COP": ["ConocoPhillips"], "SLB": ["Schlumberger", "SLB"], "HAL": ["Halliburton"],
    "BKR": ["Baker Hughes"], "MPC": ["Marathon Petroleum"], "VLO": ["Valero"], "PSX": ["Phillips 66"],
    "OXY": ["Occidental Petroleum", "Occidental"], "DOW": ["Dow Chemical", "Dow Inc"], "LYB": ["LyondellBasell"],
    "WMT": ["Walmart", "Wal-Mart"], "TGT": ["Target"], "COST": ["Costco"], "KR": ["Kroger"],
    "WBA": ["Walgreens", "Walgreen"], "CVS": ["CVS Health", "CVS Pharmacy", "Aetna"], "HD": ["Home Depot"],
    "LOW": ["Lowe's", "Lowes"], "MCD": ["McDonald's"], "SBUX": ["Starbucks"], "NKE": ["Nike"],
    "MSFT": ["Microsoft"], "GOOGL": ["Google", "Alphabet"], "META": ["Meta Platforms", "Facebook"],
    "AMZN": ["Amazon", "Amazon.com"], "NVDA": ["Nvidia", "NVIDIA"], "INTC": ["Intel"], "AMD": ["Advanced Micro Devices", "AMD"],
    "IBM": ["International Business Machines", "IBM"], "ORCL": ["Oracle America", "Oracle"], "CRM": ["Salesforce"],
    "ADBE": ["Adobe"], "CSCO": ["Cisco"], "JPM": ["JPMorgan", "JP Morgan", "Chase"], "BAC": ["Bank of America"],
    "WFC": ["Wells Fargo"], "C": ["Citibank", "Citigroup"], "GS": ["Goldman Sachs", "Goldman"],
    "MS": ["Morgan Stanley"], "AXP": ["American Express"], "COF": ["Capital One"],
    "JNJ": ["Johnson & Johnson", "J&J"], "PFE": ["Pfizer"], "MRK": ["Merck"], "ABBV": ["AbbVie"],
    "BMY": ["Bristol Myers Squibb", "Bristol-Myers"], "LLY": ["Eli Lilly", "Lilly"], "AMGN": ["Amgen"],
    "GILD": ["Gilead Sciences", "Gilead"], "UNH": ["UnitedHealth", "United Health", "Optum"],
    "VZ": ["Verizon"], "T": ["AT&T"], "CMCSA": ["Comcast"], "DIS": ["Disney", "Walt Disney"],
    "PRGO": ["Perrigo"], "HALO": ["Halozyme"],
}

HIGH_SIGNAL_ITEMS = {
    "1.01": "Material Agreement Entered", "1.02": "Material Agreement Terminated", "1.03": "Bankruptcy / Receivership",
    "2.01": "Acquisition or Disposition Completed", "2.04": "Debt Default / Acceleration Trigger", "2.05": "Restructuring / Layoffs",
    "2.06": "Material Impairment", "4.01": "Auditor Change", "4.02": "Non-Reliance on Financials",
    "5.02": "Executive / Director Change", "8.01": "Other Material Event",
}

SEC_HEADERS = {"User-Agent": os.getenv("SEC_USER_AGENT", "Everstar Research research@example.com"), "Accept-Encoding": "gzip, deflate"}

# ----------------------------- HELPERS ---------------------------------
def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fred_key():
    try:
        return st.secrets.get("FRED_API_KEY", os.getenv("FRED_API_KEY", ""))
    except Exception:
        return os.getenv("FRED_API_KEY", "")


def parse_tickers(raw):
    parts = raw.replace("\n", ",").replace(" ", ",").split(",")
    return list(dict.fromkeys([p.strip().upper() for p in parts if p.strip()]))


def pct_change_nearest(s, days):
    if len(s) < 2:
        return np.nan
    target = s.index[-1] - timedelta(days=days)
    idx = s.index.get_indexer([target], method="nearest")[0]
    base = s.iloc[idx]
    return ((s.iloc[-1] - base) / abs(base) * 100) if base != 0 else np.nan


def compute_macro_signal(s, direction):
    s = s.sort_index()
    cutoff = s.index[-1] - pd.Timedelta(weeks=52)
    window = s.loc[s.index >= cutoff]
    z = (s.iloc[-1] - window.mean()) / window.std() if len(window) > 1 and window.std() > 0 else 0.0
    adjusted_z = -z if direction == "inverted" else z
    return {
        "Latest": s.iloc[-1], "Latest Date": s.index[-1].date(), "3M %": pct_change_nearest(s, 90),
        "1Y %": pct_change_nearest(s, 365), "Z-score": z, "Adjusted Z": adjusted_z,
        "Threshold Flag": abs(adjusted_z) > 1.5,
    }


def load_fred_data(years=3):
    key = fred_key()
    if not key:
        raise RuntimeError("FRED_API_KEY is not configured. Add it to .streamlit/secrets.toml or the environment.")
    fred = Fred(api_key=key)
    start = (datetime.now() - timedelta(days=365 * years)).strftime("%Y-%m-%d")
    data, errors = {}, []
    for name, (sid, _, _) in FRED_SERIES.items():
        try:
            data[name] = fred.get_series(sid, observation_start=start).dropna()
        except Exception as e:
            errors.append(f"{name}: {e}")
    return data, errors


def load_consumer_fred(years=10):
    key = fred_key()
    if not key:
        raise RuntimeError("FRED_API_KEY is not configured.")
    fred = Fred(api_key=key)
    start = (datetime.now() - timedelta(days=365 * years)).strftime("%Y-%m-%d")
    data = {}
    for name, (sid, direction) in CONSUMER_SERIES.items():
        s = fred.get_series(sid, observation_start=start).dropna()
        data[name] = (s, direction)
    return data


def fetch_retail_series():
    r = requests.get(RETAIL_URL, headers={"User-Agent": "Everstar Research research@example.com"}, timeout=30)
    r.raise_for_status()
    xl = pd.ExcelFile(io.BytesIO(r.content), engine="openpyxl")
    years = sorted([int(s) for s in xl.sheet_names if str(s).isdigit()])
    all_data = {}
    for year in years:
        try:
            raw = pd.read_excel(xl, sheet_name=str(year), header=None, engine="openpyxl")
        except Exception:
            continue
        if len(raw) <= 6:
            continue
        header = raw.iloc[4]
        month_map = {}
        for col_idx, val in enumerate(header):
            val_str = str(val).strip()
            for m_idx, m in enumerate(MONTH_COLS):
                if val_str.startswith(m):
                    month_map[m_idx] = col_idx
                    break
        for _, row in raw.iloc[6:].iterrows():
            cat = str(row.iloc[1]).strip() if len(row) > 1 and not pd.isna(row.iloc[1]) else ""
            if not cat or cat in {"nan", "None", "NaN"} or cat.startswith(("(", "[")) or len(cat) < 5:
                continue
            monthly = {}
            for m_idx, col_idx in month_map.items():
                try:
                    v = float(row.iloc[col_idx])
                    if v > 0:
                        monthly[pd.Timestamp(year=year, month=m_idx + 1, day=1)] = v
                except Exception:
                    pass
            if monthly:
                all_data.setdefault(cat, {}).update(monthly)
    return {k: pd.Series(v).sort_index() for k, v in all_data.items() if len(v) >= 12}


def retail_total(series_dict):
    for k, s in series_dict.items():
        if "Retail and food services sales, total" in k:
            return s.dropna()
    return next(iter(series_dict.values())).dropna()


def is_senior(title):
    t = str(title or "").upper()
    return any(role.upper() in t for role in SENIOR_ROLES)


def safe_float(v):
    try:
        return float(v) if v is not None else 0.0
    except Exception:
        return 0.0


def get_owner_info(f4):
    try:
        ro = f4.reporting_owners
        owners = getattr(ro, "owners", None) or [ro]
        owner = owners[0]
        name = str(getattr(owner, "name", None) or "Unknown").strip()
        title = str(getattr(owner, "position", None) or getattr(owner, "officer_title", None) or getattr(owner, "title", None) or "").strip()
        return name, title
    except Exception:
        return "Unknown", ""


def parse_form4(f4, ticker, filing_date):
    rows = []
    owner, title = get_owner_info(f4)
    def add(code, shares, price, tx_date=None, notes=""):
        shares_f, price_f = safe_float(shares), safe_float(price)
        rows.append({"Ticker": ticker, "Insider": owner, "Title": title, "Senior": is_senior(title),
                     "Date": str(tx_date or filing_date), "Code": str(code or "").strip(),
                     "Shares": int(shares_f), "Price": round(price_f, 2), "Value ($)": round(shares_f * price_f),
                     "Filing Date": str(filing_date), "10b5-1": "10b5-1" in str(notes).lower()})
    parsed = False
    try:
        for tx in (f4.common_stock_purchases or []):
            add(getattr(tx, "transaction_code", "P") or "P", getattr(tx, "shares", None) or getattr(tx, "transaction_shares", 0),
                getattr(tx, "price", None) or getattr(tx, "transaction_price", 0), getattr(tx, "date", None) or getattr(tx, "transaction_date", filing_date), getattr(tx, "footnotes", ""))
            parsed = True
        for tx in (f4.common_stock_sales or []):
            add(getattr(tx, "transaction_code", "S") or "S", getattr(tx, "shares", None) or getattr(tx, "transaction_shares", 0),
                getattr(tx, "price", None) or getattr(tx, "transaction_price", 0), getattr(tx, "date", None) or getattr(tx, "transaction_date", filing_date), getattr(tx, "footnotes", ""))
            parsed = True
    except Exception:
        pass
    if parsed:
        return rows
    try:
        df = f4.to_dataframe()
        if df is not None and not df.empty:
            df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
            def c(*names): return next((n for n in names if n in df.columns), None)
            cc, sc, pc, dc, nc = c("transaction_code", "code"), c("transaction_shares", "shares", "amount"), c("transaction_price_per_share", "price"), c("transaction_date", "date"), c("footnotes", "notes")
            for _, r in df.iterrows():
                add(r.get(cc, "") if cc else "", r.get(sc, 0) if sc else 0, r.get(pc, 0) if pc else 0, r.get(dc, filing_date) if dc else filing_date, r.get(nc, "") if nc else "")
    except Exception:
        pass
    return rows


def scan_insiders(tickers, lookback_days, min_buy, min_sale):
    if not EDGARTOOLS_AVAILABLE:
        raise RuntimeError("edgartools is not installed.")
    identity = os.getenv("SEC_IDENTITY", "Everstar Research research@example.com")
    try:
        identity = st.secrets.get("SEC_IDENTITY", identity)
    except Exception:
        pass
    set_identity(identity)
    start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    rows = []
    for ticker in tickers:
        try:
            filings = Company(ticker).get_filings(form="4")
            recent = [f for f in filings if str(f.filing_date) >= start]
            for filing in recent:
                try:
                    rows.extend(parse_form4(filing.obj(), ticker, filing.filing_date))
                except Exception:
                    pass
                time.sleep(0.12)
        except Exception:
            pass
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Signal"] = ""
    buy = (df["Code"] == "P") & df["Senior"] & (df["Value ($)"] >= min_buy) & (~df["10b5-1"])
    sale = (df["Code"] == "S") & df["Senior"] & (df["Value ($)"] >= min_sale) & (~df["10b5-1"])
    df.loc[buy, "Signal"] = "BUY SIGNAL"
    df.loc[sale, "Signal"] = "LARGE SALE"
    buys = df[df["Signal"] == "BUY SIGNAL"].copy()
    if not buys.empty:
        buys["Week"] = pd.to_datetime(buys["Date"], errors="coerce").dt.isocalendar().week
        clusters = buys.groupby(["Ticker", "Week"]).size()
        cluster_tickers = clusters[clusters >= 2].index.get_level_values("Ticker").unique()
        df.loc[df["Ticker"].isin(cluster_tickers) & (df["Signal"] == "BUY SIGNAL"), "Signal"] = "CLUSTER BUY"
    return df.sort_values(["Signal", "Value ($)"], ascending=[True, False])


def sec_cik_map():
    r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    return {v["ticker"].upper(): str(v["cik_str"]) for v in data.values()}


def scan_8k(tickers, lookback_days):
    cikmap = sec_cik_map()
    start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    rows = []
    for ticker in tickers:
        cik = cikmap.get(ticker)
        if not cik:
            continue
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        try:
            r = requests.get(url, headers=SEC_HEADERS, timeout=15); r.raise_for_status()
            f = r.json().get("filings", {}).get("recent", {})
            for i, form in enumerate(f.get("form", [])):
                if form not in ("8-K", "8-K/A"):
                    continue
                filed = f.get("filingDate", [])[i]
                if filed < start:
                    continue
                acc = f.get("accessionNumber", [])[i]
                items = f.get("items", [""] * len(f.get("form", [])))[i] if i < len(f.get("items", [])) else ""
                primary = f.get("primaryDocument", [""] * len(f.get("form", [])))[i]
                codes = [x.strip() for x in str(items).split(",") if x.strip()]
                flagged = [c for c in codes if c in HIGH_SIGNAL_ITEMS]
                rows.append({"Ticker": ticker, "Filed": filed, "Form": form, "Items": items,
                             "Signal": "HIGH" if flagged else "standard",
                             "Descriptions": "; ".join([f"{c}: {HIGH_SIGNAL_ITEMS[c]}" for c in flagged]),
                             "URL": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{primary}"})
        except Exception:
            pass
        time.sleep(0.12)
    return pd.DataFrame(rows).sort_values("Filed", ascending=False) if rows else pd.DataFrame()


def match_warn(company, tickers):
    low = company.lower()
    for t in tickers:
        for alias in WARN_ALIASES.get(t, []):
            if alias.lower() in low:
                return t
    return None


def parse_warn_date(s):
    for fmt in ["%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(str(s).strip(), fmt)
        except Exception:
            pass
    return None


def scrape_warn_page(url, state):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15); r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        hr = table.find("tr")
        if not hr or "company" not in hr.get_text().lower():
            continue
        for tr in table.find_all("tr")[1:]:
            cols = tr.find_all(["td", "th"])
            if len(cols) < 3: continue
            rows.append({"State": state, "Company": cols[0].get_text(strip=True),
                         "Location": cols[1].get_text(strip=True) if len(cols) > 1 else "",
                         "Effective Date": cols[2].get_text(strip=True) if len(cols) > 2 else "",
                         "Employees": cols[3].get_text(strip=True) if len(cols) > 3 else "",
                         "Type": cols[4].get_text(strip=True) if len(cols) > 4 else ""})
    return rows


def scan_warn(tickers, lookback_days, states=None):
    rows = []
    try:
        rows.extend(scrape_warn_page("https://layoffalert.org", "LATEST"))
    except Exception:
        pass
    for state in (states or []):
        try:
            rows.extend(scrape_warn_page(f"https://layoffalert.org/state/{state}", state))
        except Exception:
            pass
        time.sleep(0.2)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates(subset=["Company", "Effective Date", "State"])
    df["Parsed Date"] = df["Effective Date"].apply(parse_warn_date)
    cutoff = datetime.now() - timedelta(days=lookback_days)
    df = df[df["Parsed Date"].notna() & (df["Parsed Date"] >= cutoff)].copy()
    df["Ticker"] = df["Company"].apply(lambda x: match_warn(x, tickers))
    return df.sort_values("Parsed Date", ascending=False)


def stamp(source):
    st.session_state.setdefault("updated", {})[source] = now_stamp()


def show_updated(source):
    ts = st.session_state.get("updated", {}).get(source, "Not run this session")
    st.caption(f"Last updated: {ts}")

# ----------------------------- SIDEBAR ---------------------------------
st.session_state.setdefault("portfolio_raw", "CMC, NUE, STLD, CLF, GXO, WERN, SAIA, MRK, ABBV")
st.sidebar.title("Everstar Research")
st.sidebar.text_area("Portfolio / watchlist tickers", key="portfolio_raw", height=110)
tickers = parse_tickers(st.session_state.portfolio_raw)

start_default = datetime.now().date() - timedelta(days=365 * 3)
end_default = datetime.now().date()
date_range = st.sidebar.date_input("Dashboard date range", value=(start_default, end_default))

page = st.sidebar.radio("Page", ["Macro Overview", "Consumer Health", "Supply Chain", "Insider Activity", "Corporate Stress", "Market Signals"])

st.sidebar.divider()
if st.sidebar.button("Run all connected sources", type="primary", use_container_width=True):
    errors = []
    try:
        st.session_state["macro"] = load_fred_data(3); stamp("Macro / FRED")
    except Exception as e: errors.append(f"Macro: {e}")
    try:
        st.session_state["consumer_fred"] = load_consumer_fred(10); stamp("Consumer / FRED")
        st.session_state["retail"] = fetch_retail_series(); stamp("Consumer / Census Retail")
    except Exception as e: errors.append(f"Consumer: {e}")
    try:
        st.session_state["insider"] = scan_insiders(tickers, 14, 100000, 500000); stamp("Insider / Form 4")
    except Exception as e: errors.append(f"Insider: {e}")
    try:
        st.session_state["eightk"] = scan_8k(tickers, 14); stamp("Corporate / 8-K")
        st.session_state["warn"] = scan_warn(tickers, 90); stamp("Corporate / WARN")
    except Exception as e: errors.append(f"Corporate: {e}")
    if errors:
        st.sidebar.warning("Some sources did not refresh. Open the relevant page for details.")
    else:
        st.sidebar.success("Connected sources refreshed.")

for src in ["Macro / FRED", "Consumer / FRED", "Consumer / Census Retail", "Insider / Form 4", "Corporate / WARN", "Corporate / 8-K"]:
    st.sidebar.caption(f"{src}: {st.session_state.get('updated', {}).get(src, '—')}")

# ----------------------------- PAGES ---------------------------------
if page == "Macro Overview":
    st.title("Macro Overview")
    st.caption("FRED macro dashboard: 18 series, convergence view, and weekly threshold pulse.")
    c1, c2 = st.columns([1, 4])
    if c1.button("Refresh FRED", use_container_width=True):
        try:
            st.session_state["macro"] = load_fred_data(3); stamp("Macro / FRED")
        except Exception as e: st.error(str(e))
    show_updated("Macro / FRED")

    if "macro" not in st.session_state:
        st.info("Run FRED to load the macro dashboard.")
    else:
        data, errors = st.session_state["macro"]
        rows = []
        for name, (sid, category, direction) in FRED_SERIES.items():
            if name not in data: continue
            s = data[name]
            sig = compute_macro_signal(s, direction)
            rows.append({"Category": category, "Series": name, "FRED ID": sid, **sig})
        summary = pd.DataFrame(rows)
        if not summary.empty:
            a,b,c,d = st.columns(4)
            a.metric("Series loaded", len(summary))
            b.metric("Threshold flags", int(summary["Threshold Flag"].sum()))
            c.metric("Most recent observation", str(max(summary["Latest Date"])))
            d.metric("Weekly Econ Index", f"{summary.loc[summary['Series']=='NY Fed Weekly Econ Index','Latest'].iloc[0]:.2f}" if (summary["Series"]=="NY Fed Weekly Econ Index").any() else "N/A")
            st.subheader("Weekly pulse")
            display = summary.copy()
            display["3M %"] = display["3M %"].map(lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A")
            display["1Y %"] = display["1Y %"].map(lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A")
            display["Z-score"] = display["Z-score"].map(lambda x: f"{x:+.2f}")
            st.dataframe(display[["Category","Series","Latest","Latest Date","3M %","1Y %","Z-score","Threshold Flag"]], use_container_width=True, hide_index=True)

            st.subheader("Convergence chart")
            fig, ax = plt.subplots(figsize=(12, 6))
            for name, s in data.items():
                if len(s) < 2: continue
                s2 = s[s.index >= pd.Timestamp(date_range[0])] if isinstance(date_range, (tuple, list)) and len(date_range) == 2 else s
                if len(s2) < 2: continue
                norm = (s2 / s2.iloc[0] - 1) * 100
                ax.plot(norm.index, norm.values, linewidth=1, alpha=.65, label=name)
            ax.axhline(0, linewidth=.8)
            ax.set_ylabel("Change from start of selected period (%)")
            ax.set_title("Macro series normalized to selected-period starting value")
            ax.legend(fontsize=6, ncol=3, loc="upper left")
            st.pyplot(fig, clear_figure=True)

            st.subheader("All 18 series")
            selected = st.selectbox("Series detail", list(data.keys()))
            s = data[selected]
            if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
                s = s[(s.index.date >= date_range[0]) & (s.index.date <= date_range[1])]
            st.line_chart(s.rename(selected))
        if errors:
            with st.expander("FRED load errors"):
                st.write(errors)

elif page == "Consumer Health":
    st.title("Consumer Health")
    st.caption("Census retail sales plus FRED savings, credit, revolving credit, and credit-card delinquency data.")
    c1,c2,c3 = st.columns([1,1,4])
    if c1.button("Refresh consumer FRED", use_container_width=True):
        try: st.session_state["consumer_fred"] = load_consumer_fred(10); stamp("Consumer / FRED")
        except Exception as e: st.error(str(e))
    if c2.button("Refresh retail sales", use_container_width=True):
        try: st.session_state["retail"] = fetch_retail_series(); stamp("Consumer / Census Retail")
        except Exception as e: st.error(str(e))
    show_updated("Consumer / FRED"); show_updated("Consumer / Census Retail")

    if "retail" in st.session_state:
        s = retail_total(st.session_state["retail"])
        yoy = s.pct_change(12) * 100
        mom = s.pct_change(1) * 100
        smooth = yoy.rolling(3).mean()
        a,b,c,d = st.columns(4)
        a.metric("Latest retail sales ($M)", f"{s.iloc[-1]:,.0f}")
        b.metric("Retail YoY", f"{yoy.iloc[-1]:+.1f}%")
        c.metric("Retail MoM", f"{mom.iloc[-1]:+.1f}%")
        d.metric("3M avg YoY", f"{smooth.iloc[-1]:+.1f}%")
        st.subheader("Retail sales — smoothed YoY")
        st.line_chart(pd.DataFrame({"YoY %": yoy, "3M average YoY %": smooth}))
    else:
        st.info("Retail sales have not been loaded this session.")

    if "consumer_fred" in st.session_state:
        data = st.session_state["consumer_fred"]
        rows = []
        for name, (s, direction) in data.items():
            yoy = s.pct_change(12).dropna()
            cutoff = s.index[-1] - pd.DateOffset(months=12)
            w = s.loc[s.index >= cutoff]
            z = (s.iloc[-1]-w.mean())/w.std() if len(w)>1 and w.std()>0 else 0
            rows.append({"Series": name, "Latest": s.iloc[-1], "Date": s.index[-1].date(), "YoY %": yoy.iloc[-1] if len(yoy) else np.nan, "Z-score": z})
        st.subheader("Consumer balance-sheet indicators")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        fig, axes = plt.subplots(2,2, figsize=(12,7))
        for ax, (name,(s,_)) in zip(axes.flatten(), data.items()):
            ax.plot(s.index, s.values, linewidth=1.4)
            ax.set_title(name, fontsize=9)
            ax.tick_params(labelsize=7)
        fig.tight_layout(); st.pyplot(fig, clear_figure=True)
    else:
        st.info("Consumer FRED series have not been loaded this session.")

elif page == "Supply Chain":
    st.title("Supply Chain")
    st.info("Placeholder — dedicated supply-chain data pipeline is not connected yet.")
    st.subheader("Planned sources")
    st.write("AAR rail data by commodity category, plus shipping indices such as BDI and FBX from non-terminal sources.")
    st.caption("No placeholder values or synthetic charts are displayed on this page.")

elif page == "Insider Activity":
    st.title("Insider Activity")
    st.caption("SEC Form 4 scanner using the portfolio/watchlist from the sidebar.")
    c1,c2,c3 = st.columns(3)
    lookback = c1.number_input("Lookback days", min_value=1, max_value=180, value=14)
    min_buy = c2.number_input("Minimum purchase value ($)", min_value=0, value=100000, step=25000)
    min_sale = c3.number_input("Minimum sale value ($)", min_value=0, value=500000, step=50000)
    if st.button("Run Form 4 scan", type="primary"):
        try:
            st.session_state["insider"] = scan_insiders(tickers, int(lookback), int(min_buy), int(min_sale)); stamp("Insider / Form 4")
        except Exception as e: st.error(str(e))
    show_updated("Insider / Form 4")
    if "insider" in st.session_state:
        df = st.session_state["insider"]
        if df.empty:
            st.info("No transactions were parsed for the selected tickers and lookback window.")
        else:
            flagged = df[df["Signal"] != ""].sort_values("Value ($)", ascending=False)
            a,b,c = st.columns(3)
            a.metric("Transactions parsed", len(df)); b.metric("Flagged transactions", len(flagged)); c.metric("Tickers with filings", df["Ticker"].nunique())
            st.subheader("Flagged transactions")
            st.dataframe(flagged, use_container_width=True, hide_index=True)
            with st.expander("All parsed transactions"):
                st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Run the scanner to populate this page.")

elif page == "Corporate Stress":
    st.title("Corporate Stress")
    st.caption("WARN Act filings and SEC 8-K material-event monitoring.")
    c1,c2,c3 = st.columns([1,1,3])
    warn_days = c1.number_input("WARN lookback", 1, 365, 90)
    k_days = c2.number_input("8-K lookback", 1, 90, 14)
    warn_states = st.multiselect("Optional state pages to scan in addition to the latest page", ["ca","ny","tx","fl","pa","nj","ct","ma","il","oh","nc","sc","ga","mi","wa"], default=[])
    a,b = st.columns(2)
    if a.button("Run WARN scan", use_container_width=True):
        try: st.session_state["warn"] = scan_warn(tickers, int(warn_days), warn_states); stamp("Corporate / WARN")
        except Exception as e: st.error(str(e))
    if b.button("Run 8-K scan", use_container_width=True):
        try: st.session_state["eightk"] = scan_8k(tickers, int(k_days)); stamp("Corporate / 8-K")
        except Exception as e: st.error(str(e))
    show_updated("Corporate / WARN"); show_updated("Corporate / 8-K")

    st.subheader("WARN Act")
    if "warn" in st.session_state:
        df = st.session_state["warn"]
        if df.empty: st.info("No WARN rows were returned for the selected scan.")
        else:
            hits = df[df["Ticker"].notna()]
            st.metric("Portfolio/watchlist matches", len(hits))
            st.dataframe(hits[["Ticker","Company","Location","State","Effective Date","Employees","Type"]], use_container_width=True, hide_index=True)
            with st.expander("All recent WARN rows collected"):
                st.dataframe(df, use_container_width=True, hide_index=True)
    else: st.info("WARN data has not been loaded this session.")

    st.subheader("8-K monitor")
    if "eightk" in st.session_state:
        df = st.session_state["eightk"]
        if df.empty: st.info("No 8-K filings were returned for the selected scan.")
        else:
            a,b,c = st.columns(3); a.metric("8-K filings", len(df)); b.metric("High-signal item filings", int((df["Signal"]=="HIGH").sum())); c.metric("Tickers with 8-Ks", df["Ticker"].nunique())
            st.dataframe(df[["Ticker","Filed","Form","Items","Signal","Descriptions","URL"]], use_container_width=True, hide_index=True, column_config={"URL": st.column_config.LinkColumn("SEC filing")})
    else: st.info("8-K data has not been loaded this session.")

else:
    st.title("Market Signals")
    st.info("Placeholder — market-signal feeds are not connected yet.")
    st.subheader("Planned sources")
    st.write("Kalshi prediction-market probabilities and congressional trading data from CapitolTrades.")
    st.caption("No placeholder values or synthetic charts are displayed on this page.")