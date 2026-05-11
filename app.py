import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import yfinance as yf
import tweepy
import requests

st.set_page_config(page_title="Call Buying Pro", layout="wide", initial_sidebar_state="expanded")

st.title("🚀 Call Buying Readiness Pro")
st.caption("Live yfinance • Real X Options Flow • Telegram Alerts")

# ====================== SECRETS & SETUP ======================
st.sidebar.header("🔑 API Setup")
st.sidebar.caption("Add these in Streamlit → Manage app → Secrets")

X_BEARER = st.secrets.get("x", {}).get("bearer_token")
TG_TOKEN = st.secrets.get("telegram", {}).get("bot_token")
TG_CHAT_ID = st.secrets.get("telegram", {}).get("chat_id")

if not X_BEARER:
    st.sidebar.warning("⚠️ X Bearer Token not set in secrets")
if not TG_TOKEN or not TG_CHAT_ID:
    st.sidebar.warning("⚠️ Telegram Bot Token + Chat ID not set in secrets")

# ====================== LIVE MARKET DATA ======================
@st.cache_data(ttl=60)
def get_live_data(tickers):
    data = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose") or 0
            iv_rank_est = max(20, min(80, 100 - (price / max(info.get("fiftyTwoWeekHigh", price+1), 1) * 50)))
            score = round(4 + (80 - iv_rank_est) * 0.08, 1)
            data.append({
                "Ticker": ticker, "Price": round(price, 2), "Score": score,
                "IV_Rank": int(iv_rank_est), "Readiness": "Strong Buy Call" if iv_rank_est < 45 else "Buy Call" if iv_rank_est < 65 else "Monitor",
                "Risk_1_Contract": int(price * 0.8)
            })
        except:
            pass
    return pd.DataFrame(data)

watchlist = st.sidebar.multiselect("Permanent Watchlist", 
    ["MSFT", "META", "NFLX", "LLY", "CVX", "XOM", "MU", "CVNA", "INTC", "TSLA", "NVDA", "AAPL"],
    default=["MSFT", "META", "NFLX", "MU", "CVNA"])

df = get_live_data(watchlist)

# ====================== REAL-TIME X SIGNALS ======================
@st.cache_data(ttl=300)  # 5 min cache
def get_x_signals():
    if not X_BEARER:
        return pd.DataFrame([{"Ticker": "-", "Signal": "X API not configured", "Source": "Setup required", "Time": "Now"}])
    
    try:
        client = tweepy.Client(bearer_token=X_BEARER)
        query = "call OR sweep OR flow OR unusual (MU OR CVNA OR NFLX OR TSLA OR META OR MSFT) -is:retweet lang:en"
        tweets = client.search_recent_tweets(
            query=query,
            max_results=20,
            tweet_fields=["created_at", "author_id"]
        )
        
        signals = []
        if tweets.data:
            for tweet in tweets.data[:8]:
                text = tweet.text[:120] + "..." if len(tweet.text) > 120 else tweet.text
                signals.append({
                    "Ticker": "Multiple" if any(t in text.upper() for t in watchlist) else "General",
                    "Signal": text,
                    "Source": "@X_Flow",
                    "Time": tweet.created_at.strftime("%H:%M")
                })
        return pd.DataFrame(signals) if signals else pd.DataFrame([{"Ticker": "-", "Signal": "No recent flow found", "Source": "X API", "Time": "Now"}])
    except Exception as e:
        return pd.DataFrame([{"Ticker": "-", "Signal": f"API Error: {str(e)[:80]}", "Source": "X API", "Time": "Now"}])

x_signals = get_x_signals()

# ====================== TELEGRAM ALERTS ======================
def send_telegram_alert(message):
    if TG_TOKEN and TG_CHAT_ID:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload)
            return True
        except:
            return False
    return False

# ====================== UI ======================
if st.sidebar.button("🔄 Refresh All Data"):
    st.rerun()

min_score = st.sidebar.slider("Minimum Score", 0.0, 10.0, 6.5, 0.1)
show_strong_only = st.sidebar.checkbox("Show Only Strong Buy / Buy Call", value=True)

df_filtered = df[df["Score"] >= min_score].copy()
if show_strong_only:
    df_filtered = df_filtered[df_filtered["Readiness"].str.contains("Strong|Buy Call", regex=True)]

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Scanner", "📈 Charts", "💰 Simulator", "🔥 Real X Signals", "🛎️ Telegram Alerts"])

with tab1:
    st.subheader("Strong Buy Call Candidates")
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
    st.subheader("🔥 Real-Time X Options Flow")
    st.caption("Fetched live via X API v2 (updates every 5 min)")
    st.dataframe(x_signals, use_container_width=True)
    if st.button("🔄 Refresh X Signals Now"):
        st.cache_data.clear()
        st.rerun()

with tab5:
    st.subheader("🛎️ Telegram Alerts")
    st.write("Get instant alerts when a Strong Buy Call appears or new X flow is detected.")
    
    if st.button("📤 Send Test Telegram Alert", type="primary"):
        test_msg = f"🧪 Test Alert from Call Buying Pro\nTime: {datetime.now().strftime('%H:%M')}\nStrong signals detected!"
        if send_telegram_alert(test_msg):
            st.success("✅ Test message sent to your Telegram!")
        else:
            st.error("Telegram not configured. Add secrets.")

    st.caption("""
    **Setup Telegram in 2 minutes:**
    1. Talk to @BotFather on Telegram → /newbot → get **BOT_TOKEN**
    2. Send any message to your bot → go to https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates → copy **chat_id**
    3. In Streamlit Secrets add:
