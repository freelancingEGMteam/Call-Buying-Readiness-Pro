import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
import requests

st.set_page_config(page_title="Call Buying Pro", layout="wide", initial_sidebar_state="expanded")

st.title("🚀 Call Buying Readiness Pro")
st.caption("High-Volume • 15–40% from 52W High • 12–90 DTE • Call Premium ≤ $3.00")

# ====================== SECRETS ======================
TG_TOKEN = st.secrets.get("telegram", {}).get("bot_token")
TG_CHAT_ID = st.secrets.get("telegram", {}).get("chat_id")

# ====================== DYNAMIC SCANNER ======================
@st.cache_data(ttl=600)
def get_options_scanner():
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
            
            # 12–90 DTE + premium ≤ $3.00 (no minimum)
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
                    good_calls = calls[calls['lastPrice'] <= 3.0]
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

# ====================== TELEGRAM ======================
def send_telegram_alert(message):
    if TG_TOKEN and TG_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                          json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"})
            return True
        except:
            return False
    return False

# ====================== UI ======================
if st.sidebar.button("🔄 Refresh All Market Data"):
    st.rerun()

min_score = st.sidebar.slider("Minimum Score", 0.0, 10.0, 6.5, 0.1)
show_strong_only = st.sidebar.checkbox("Show Only Strong Buy / Buy Call", value=True)

df_filtered = df_scanner[df_scanner["Score"] >= min_score].copy()
if show_strong_only:
    df_filtered = df_filtered[df_filtered["Readiness"].str.contains("Strong|Buy Call", regex=True)]

tab1, tab2 = st.tabs(["📊 Scanner", "🛎️ Telegram Alerts"])

with tab1:
    st.subheader("Strong Buy Call Candidates (12–90 DTE + Call Premium ≤ $3.00)")
    
    with st.expander("📋 Column Legend"):
        st.markdown("""
        | Column              | Meaning |
        |---------------------|---------|
        | **Price**           | Current stock price |
        | **52W_High**        | 52-week highest price |
        | **Percent_From_High** | Distance below 52W high (ideal: -15% to -40%) |
        | **Score**           | Call-buying readiness score (higher = better) |
        | **IV_Rank**         | Implied volatility rank (lower = cheaper options) |
        | **DTE**             | Days to expiration (12–90 days) |
        | **Call_Premium**    | Price of call option (≤ $3.00) |
        | **Daily_Volume**    | Shares traded today (≥ 1 million) |
        | **Readiness**       | Strong Buy Call / Buy Call / Monitor |
        | **Risk_1_Contract** | Approx. cost for 1 call contract |
        """)
    
    if df_filtered.empty:
        st.info("**No stocks currently meet all criteria.**\n\nTry lowering the Minimum Score slider or unchecking 'Show Only Strong Buy / Buy Call'.")
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

with tab2:
    st.subheader("🛎️ Telegram Alerts")
    if st.button("📤 Send Test Telegram Alert", type="primary"):
        msg = f"🧪 Test Alert from Call Buying Pro\nTime: {datetime.now().strftime('%H:%M')}"
        if send_telegram_alert(msg):
            st.success("✅ Sent to Telegram!")
        else:
            st.error("Telegram not configured")

st.divider()
st.caption("✅ Dashboard simplified • Only Scanner + Telegram Alerts")
