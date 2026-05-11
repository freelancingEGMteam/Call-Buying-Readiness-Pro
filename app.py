import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import yfinance as yf
import tweepy
import requests

st.set_page_config(page_title="Call Buying Pro", layout="wide", initial_sidebar_state="expanded")

st.title("🚀 Call Buying Readiness Pro")
st.caption("Live Prices • Manual X Options Flow • Telegram Alerts")

# ====================== SECRETS ======================
X_BEARER = st.secrets.get("x", {}).get("bearer_token")
TG_TOKEN = st.secrets.get("telegram", {}).get("bot_token")
TG_CHAT_ID = st.secrets.get("telegram", {}).get("chat_id")

# ====================== LIVE DATA (unchanged) ======================
@st.cache_data(ttl=300)
def get_live_data(tickers):
    data = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose") or 0
            if price > 0:
                iv_rank_est = max(20, min(80, 100 - (price / max(info.get("fiftyTwoWeekHigh", price + 1), 1) * 50)))
                score = round(4 + (80 - iv_rank_est) * 0.08, 1)
                data.append({
                    "Ticker": ticker, "Price": round(price, 2), "Score": score,
                    "IV_Rank": int(iv_rank_est),
                    "Readiness": "Strong Buy Call" if iv_rank_est < 45 else "Buy Call" if iv_rank_est < 65 else "Monitor",
                    "Risk_1_Contract": int(price * 0.8)
                })
        except:
            pass

    df = pd.DataFrame(data)
    if len(df) < 2:
        st.warning("⚠️ Live prices temporarily unavailable — showing sample data")
        df = pd.DataFrame([
            {"Ticker": "NFLX", "Price": 87.4, "Score": 8.6, "IV_Rank": 26, "Readiness": "Strong Buy Call", "Risk_1_Contract": 450},
            {"Ticker": "MU",   "Price": 798.5, "Score": 8.7, "IV_Rank": 42, "Readiness": "Strong Buy Call", "Risk_1_Contract": 1250},
            {"Ticker": "CVNA", "Price": 287.2, "Score": 8.1, "IV_Rank": 35, "Readiness": "Strong Buy Call", "Risk_1_Contract": 850},
            {"Ticker": "META", "Price": 609.8, "Score": 7.6, "IV_Rank": 31, "Readiness": "Buy Call", "Risk_1_Contract": 1800},
        ])
    return df

watchlist = st.sidebar.multiselect("Permanent Watchlist", 
    ["MSFT", "META", "NFLX", "LLY", "CVX", "XOM", "MU", "CVNA", "INTC", "TSLA", "NVDA", "AAPL"],
    default=["MSFT", "META", "NFLX", "MU", "CVNA"])

df = get_live_data(watchlist)

# ====================== IMPROVED X SIGNALS (much tighter query) ======================
@st.cache_data(ttl=86400)
def get_x_signals():
    if not X_BEARER:
        return pd.DataFrame([{"Ticker": "-", "Signal": "Add X Bearer Token in Secrets", "Source": "X API", "Time": "Now"}])
    
    try:
        client = tweepy.Client(bearer_token=X_BEARER)
        
        # Much more targeted query for REAL options flow
        query = (
            '("call sweep" OR "sweep call" OR "call block" OR "unusual call" OR '
            '"options flow" OR "big call" OR "0DTE call" OR "unusual options" OR '
            '"call buying" OR "flow alert") '
            '(MU OR CVNA OR NFLX OR TSLA OR META OR MSFT OR INTC OR NVDA OR AAPL) '
            '-is:retweet lang:en'
        )
        
        tweets = client.search_recent_tweets(
            query=query,
            max_results=20,
            tweet_fields=["created_at"]
        )
        
        signals = []
        if tweets.data:
            for tweet in tweets.data[:12]:
                text = tweet.text[:180] + "..." if len(tweet.text) > 180 else tweet.text
                signals.append({
                    "Ticker": "Multiple",
                    "Signal": text,
                    "Source": "@X_Flow",
                    "Time": tweet.created_at.strftime("%b %d %H:%M")
                })
        return pd.DataFrame(signals) if signals else pd.DataFrame([{"Ticker": "-", "Signal": "No strong options flow found in the last few hours", "Source": "X API", "Time": "Now"}])
    except Exception as e:
        return pd.DataFrame([{"Ticker": "-", "Signal": f"Error: {str(e)[:100]}", "Source": "X API", "Time": "Now"}])

# ====================== TELEGRAM (unchanged) ======================
def send_telegram_alert(message):
    if TG_TOKEN and TG_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                          json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"})
            return True
        except:
            return False
    return False

# ====================== UI (unchanged) ======================
if st.sidebar.button("🔄 Refresh All Market Data"):
    st.rerun()

min_score = st.sidebar.slider("Minimum Score", 0.0, 10.0, 6.5, 0.1)
show_strong_only = st.sidebar.checkbox("Show Only Strong Buy / Buy Call", value=True)

df_filtered = df[df["Score"] >= min_score].copy()
if show_strong_only:
    df_filtered = df_filtered[df_filtered["Readiness"].str.contains("Strong|Buy Call", regex=True)]

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Scanner", "📈 Charts", "💰 Simulator", "🔥 Manual X Signals", "🛎️ Telegram Alerts"])

with tab1:
    st.subheader("Strong Buy Call Candidates")
    if df_filtered.empty:
        st.info("No candidates match your filters. Try lowering the score or unchecking the filter.")
        st.dataframe(df.style.background_gradient(subset=["Score"], cmap="RdYlGn"), use_container_width=True)
    else:
        st.dataframe(df_filtered.style.background_gradient(subset=["Score"], cmap="RdYlGn"), use_container_width=True, height=400)

with tab2:
    st.subheader("Score Distribution")
    fig = px.bar(df, x="Ticker", y="Score", color="Readiness")
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("1-Contract Simulator")
    selected = st.selectbox("Select Ticker", df["Ticker"])
    contracts = st.slider("Contracts", 1, 20, 1)
    row = df[df["Ticker"] == selected].iloc[0]
    total = row['Risk_1_Contract'] * contracts
    st.metric("Total Cost", f"${total:,}")
    upside = st.slider("Expected Move %", 5, 60, 20)
    profit = int(total * (upside / 20))
    st.success(f"Potential Profit: **${profit:,}** (+{upside}%)")
    st.warning(f"Max Loss: **-${total:,}**")

with tab4:
    st.subheader("🔥 Manual X Options Flow Pull")
    st.caption("Now filtered for real options sweeps, blocks & flow alerts")
    if st.button("🚀 Pull Latest X Signals Now", type="primary", use_container_width=True):
        with st.spinner("Fetching real options flow..."):
            x_signals = get_x_signals()
            st.cache_data.clear()
        st.success("✅ Latest signals loaded!")
    x_signals = get_x_signals()
    st.dataframe(x_signals, use_container_width=True)

with tab5:
    st.subheader("🛎️ Telegram Alerts")
    if st.button("📤 Send Test Telegram Alert", type="primary"):
        msg = f"🧪 Test Alert from Call Buying Pro\nTime: {datetime.now().strftime('%H:%M')}"
        if send_telegram_alert(msg):
            st.success("✅ Sent to Telegram!")
        else:
            st.error("Telegram not configured")

st.divider()
st.caption("✅ Much cleaner options flow query • Click the red button to test")
