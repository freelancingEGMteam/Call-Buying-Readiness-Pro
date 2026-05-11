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

# ====================== FOREX SWING SIGNALS (HIGH CONFIDENCE ONLY) ======================
@st.cache_data(ttl=300)
def get_forex_swing_signals():
    pairs = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"]
    data = []
    for pair in pairs:
        try:
            ticker = yf.Ticker(pair)
            hist = ticker.history(period="90d")
            if len(hist) < 30: continue
                
            current_price = hist['Close'].iloc[-1]
            ema200 = hist['Close'].ewm(span=200).mean().iloc[-1]
            rsi = 100 - (100 / (1 + (hist['Close'].diff(1).clip(lower=0).ewm(span=14).mean() / 
                                      hist['Close'].diff(1).clip(upper=0).abs().ewm(span=14).mean())))
            rsi = rsi.iloc[-1]
            
            direction = "Bullish" if current_price > ema200 and rsi < 70 else "Bearish" if current_price < ema200 and rsi > 30 else "Neutral"
            
            # Only High Confidence
            if abs(rsi - 50) <= 15:
                continue
                
            recent_high = hist['High'].rolling(20).max().iloc[-1]
            recent_low = hist['Low'].rolling(20).min().iloc[-1]
            
            if direction == "Bullish":
                entry = round(current_price, 4)
                target1 = round(recent_high * 1.015, 4)
                stop = round(recent_low * 0.985, 4)
            else:
                entry = round(current_price, 4)
                target1 = round(recent_low * 0.985, 4)
                stop = round(recent_high * 1.015, 4)
            
            rr = round((abs(target1 - entry) / abs(entry - stop)), 2) if abs(entry - stop) > 0 else 0
            
            data.append({
                "Pair": pair.replace("=X", ""),
                "Direction": direction,
                "Price": round(current_price, 4),
                "RSI": round(rsi, 1),
                "Entry": entry,
                "Target 1": target1,
                "Stop Loss": stop,
                "R:R": rr,
                "Confidence": "High"
            })
        except:
            continue
    df = pd.DataFrame(data)
    return df.sort_values(by="R:R", ascending=False)

# ====================== SCANNER & X SIGNALS (unchanged) ======================
# ... (your existing scanner + X signals code remains the same) ...

# ====================== UI ======================
if st.sidebar.button("🔄 Refresh All Market Data"):
    st.rerun()

tab1, tab4, tab5, tab6 = st.tabs(["📊 Scanner", "🔥 Manual X Signals", "🛎️ Telegram Alerts", "🌍 Forex Swing Signals"])

with tab6:
    st.subheader("🌍 Forex Swing Signals — High Confidence Only")
    st.caption("Updated every 5 minutes • Only strong setups shown")
    
    forex_signals = get_forex_swing_signals()
    
    if forex_signals.empty:
        st.info("No High Confidence swing setups at the moment.")
    else:
        st.dataframe(
            forex_signals.style.background_gradient(subset=["R:R"], cmap="RdYlGn"),
            column_config={
                "Price": st.column_config.NumberColumn(format="%.4f"),
                "Entry": st.column_config.NumberColumn(format="%.4f"),
                "Target 1": st.column_config.NumberColumn(format="%.4f"),
                "Stop Loss": st.column_config.NumberColumn(format="%.4f"),
                "R:R": st.column_config.NumberColumn(format="%.2f"),
            },
            use_container_width=True,
            height=500
        )

st.divider()
st.caption("✅ Forex tab now shows **only High Confidence** signals")
