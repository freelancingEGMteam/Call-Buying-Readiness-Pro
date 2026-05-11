import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
import tweepy
import requests
import re

st.set_page_config(page_title="Call Buying Pro", layout="wide", initial_sidebar_state="expanded")

st.title("🚀 Call Buying Readiness Pro")
st.caption("High-Volume • 15–40% from 52W High • 12–90 DTE • Call Premium ≤ $3")

# ====================== SECRETS ======================
X_BEARER = st.secrets.get("x", {}).get("bearer_token")
TG_TOKEN = st.secrets.get("telegram", {}).get("bot_token")
TG_CHAT_ID = st.secrets.get("telegram", {}).get("chat_id")

# ====================== X FLOW WATCHLIST ======================
x_watchlist = st.sidebar.multiselect(
    "X Flow Watchlist (signals only)",
    ["MSFT", "META", "NFLX", "LLY", "MU", "CVNA", "INTC", "TSLA", "NVDA", "AAPL"],
    default=["MU", "CVNA", "NFLX", "TSLA", "META"]
)

# ====================== FOREX PAIRS ======================
FOREX_PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"]

# ====================== DYNAMIC SCANNER (unchanged) ======================
@st.cache_data(ttl=600)
def get_options_scanner():
    # ... (your existing scanner code - unchanged) ...
    data = []
    today = datetime.now().date()
    for ticker in ["MSFT","META","NFLX","LLY","MU","CVNA","INTC","TSLA","NVDA","AAPL","AMD","AMZN","GOOGL","SMCI","AVGO","CRM","ADBE","ORCL","NOW","PLTR","HOOD"]:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            volume = info.get("regularMarketVolume") or info.get("volume") or 0
            if volume < 1_000_000: continue
            market_cap = info.get("marketCap") or 0
            if market_cap < 50_000_000_000: continue
            price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose") or 0
            if price == 0: continue
            high_52w = info.get("fiftyTwoWeekHigh")
            if not high_52w: continue
            percent_from_high = ((price / high_52w) - 1) * 100
            if not (-40 <= percent_from_high <= -15): continue
            
            expirations = stock.options
            suitable_call = False
            best_premium = None
            dte = None
            for exp in expirations[:8]:
                exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
                days = (exp_date - today).days
                if 12 <= days <= 90:
                    chain = stock.option_chain(exp)
                    calls = chain.calls
                    good_calls = calls[(calls['lastPrice'] >= 2.5) & (calls['lastPrice'] <= 3.0)]
                    if not good_calls.empty:
                        suitable_call = True
                        best_premium = round(good_calls['lastPrice'].iloc[0], 2)
                        dte = days
                        break
            if not suitable_call: continue
            
            iv_rank_est = max(20, min(80, 100 - (price / high_52w * 50)))
            score = round(4 + (80 - iv_rank_est) * 0.08 + (best_premium or 3) * 0.3, 1)
            readiness = "Strong Buy Call" if iv_rank_est < 45 else "Buy Call" if iv_rank_est < 65 else "Monitor"
            
            data.append({
                "Ticker": ticker,
                "Price": round(price, 2),
                "52W_High": round(high_52w, 2),
                "Percent_From_High": f"{percent_from_high:.1f}%",
                "Score": score,
                "IV_Rank": int(iv_rank_est),
                "DTE": dte,
                "Call_Premium": best_premium,
                "Daily_Volume": f"{int(volume):,}",
                "Readiness": readiness,
                "Risk_1_Contract": int(price * 0.8)
            })
        except:
            continue
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values(by="Score", ascending=False).reset_index(drop=True)
    return df

df_scanner = get_options_scanner()

# ====================== FOREX ANALYSIS ======================
@st.cache_data(ttl=60)
def get_forex_data():
    data = []
    for pair in FOREX_PAIRS:
        try:
            ticker = yf.Ticker(pair)
            info = ticker.info
            price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose") or 0
            change = info.get("regularMarketChangePercent", 0)
            high_52w = info.get("fiftyTwoWeekHigh", 0)
            low_52w = info.get("fiftyTwoWeekLow", 0)
            
            data.append({
                "Pair": pair.replace("=X", ""),
                "Rate": round(price, 4),
                "Daily %": round(change, 2),
                "52W High": round(high_52w, 4),
                "52W Low": round(low_52w, 4),
            })
        except:
            continue
    return pd.DataFrame(data)

# ====================== MANUAL X SIGNALS ======================
@st.cache_data(ttl=86400)
def get_x_signals():
    # (your existing X signals code - unchanged)
    if not X_BEARER:
        return pd.DataFrame([{"Ticker": "-", "Signal": "Add X Bearer Token in Secrets", "Source": "X API", "Time": "Now"}])
    try:
        client = tweepy.Client(bearer_token=X_BEARER)
        tickers_str = " OR ".join(x_watchlist)
        query = (
            '("call sweep" OR "sweep call" OR "call block" OR "unusual call" OR '
            '"options flow" OR "big call" OR "0DTE call" OR "unusual options" OR "call buying") '
            f'({tickers_str}) -is:retweet lang:en'
        )
        tweets = client.search_recent_tweets(query=query, max_results=20, tweet_fields=["created_at"], expansions=["author_id"], user_fields=["username"])
        signals = []
        known_tickers = set(x_watchlist)
        if tweets.data:
            users = {u.id: u.username for u in tweets.includes.get("users", [])}
            for tweet in tweets.data[:12]:
                text = tweet.text
                username = users.get(tweet.author_id, "unknown")
                dt_est = tweet.created_at - timedelta(hours=4)
                time_est = dt_est.strftime("%b %d %H:%M") + " EST"
                extracted = re.findall(r'\b([A-Z]{2,5})\b', text)
                detected = [t for t in extracted if t in known_tickers]
                ticker_display = detected[0] if detected else "Multiple"
                signals.append({"Ticker": ticker_display, "Signal": text, "Source": f"@{username}", "Time": time_est})
        return pd.DataFrame(signals) if signals else pd.DataFrame([{"Ticker": "-", "Signal": "No recent flow found", "Source": "X API", "Time": "Now"}])
    except:
        return pd.DataFrame([{"Ticker": "-", "Signal": "X API error", "Source": "X API", "Time": "Now"}])

# ====================== UI ======================
if st.sidebar.button("🔄 Refresh All Market Data"):
    st.rerun()

min_score = st.sidebar.slider("Minimum Score", 0.0, 10.0, 6.5, 0.1)
show_strong_only = st.sidebar.checkbox("Show Only Strong Buy / Buy Call", value=True)

df_filtered = df_scanner[df_scanner["Score"] >= min_score].copy()
if show_strong_only:
    df_filtered = df_filtered[df_filtered["Readiness"].str.contains("Strong|Buy Call", regex=True)]

tab1, tab4, tab5, tab6 = st.tabs(["📊 Scanner", "🔥 Manual X Signals", "🛎️ Telegram Alerts", "🌍 Forex"])

with tab1:
    st.subheader("Strong Buy Call Candidates (12–90 DTE + Call Premium ≤ $3)")
    # ... (your existing scanner code with the empty table handling) ...
    with st.expander("📋 Column Legend"):
        st.markdown("""... (your legend) ...""")
    if df_filtered.empty:
        st.info("No stocks currently meet all criteria...")
    else:
        st.dataframe(
            df_filtered.style.background_gradient(subset=["Score"], cmap="RdYlGn"),
            column_config={
                "Price": st.column_config.NumberColumn(format="%.1f"),
                "52W_High": st.column_config.NumberColumn(format="%.1f"),
                "Score": st.column_config.NumberColumn(format="%.1f"),
                "Call_Premium": st.column_config.NumberColumn(format="%.1f"),
                "Risk_1_Contract": st.column_config.NumberColumn(format="%d"),
            },
            use_container_width=True,
            height=550
        )

with tab4:
    st.subheader("🔥 Manual X Options Flow Pull")
    # ... (your existing X signals code with Analyze buttons) ...

with tab5:
    st.subheader("🛎️ Telegram Alerts")
    # ... (your existing telegram code) ...

with tab6:
    st.subheader("🌍 Forex Analysis")
    st.caption("Live major currency pairs")
    
    forex_df = get_forex_data()
    
    st.dataframe(
        forex_df.style.background_gradient(subset=["Daily %"], cmap="RdYlGn"),
        column_config={
            "Rate": st.column_config.NumberColumn(format="%.4f"),
            "Daily %": st.column_config.NumberColumn(format="%.2f"),
            "52W High": st.column_config.NumberColumn(format="%.4f"),
            "52W Low": st.column_config.NumberColumn(format="%.4f"),
        },
        use_container_width=True,
        height=400
    )

    st.info("More Forex features (technical analysis, economic calendar, sentiment) can be added next — just tell me what you want!")

st.divider()
st.caption("✅ New Forex tab added • Scanner table hidden when empty")
