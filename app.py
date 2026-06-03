import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm
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

# ====================== GEX ENGINE ======================
def bs_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        return norm.pdf(d1) / (S * sigma * np.sqrt(T))
    except Exception:
        return 0.0

@st.cache_data(ttl=300)
def compute_gex(ticker_symbol):
    stock = yf.Ticker(ticker_symbol)
    info = stock.info
    spot = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
    if not spot:
        return None, None, {}

    today = datetime.now().date()
    r = 0.05
    gex_by_strike = {}

    expirations = stock.options
    for exp in expirations[:10]:
        try:
            exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
            T = (exp_date - today).days / 365.0
            if T <= 0:
                continue

            chain = stock.option_chain(exp)

            for _, row in chain.calls.iterrows():
                K = row.get('strike', 0)
                sigma = row.get('impliedVolatility', 0) or 0
                oi = int(row.get('openInterest', 0) or 0)
                if K <= 0 or sigma <= 0 or oi <= 0:
                    continue
                g = bs_gamma(spot, K, T, r, sigma)
                gex_by_strike[K] = gex_by_strike.get(K, 0.0) + g * oi * 100 * spot

            for _, row in chain.puts.iterrows():
                K = row.get('strike', 0)
                sigma = row.get('impliedVolatility', 0) or 0
                oi = int(row.get('openInterest', 0) or 0)
                if K <= 0 or sigma <= 0 or oi <= 0:
                    continue
                g = bs_gamma(spot, K, T, r, sigma)
                gex_by_strike[K] = gex_by_strike.get(K, 0.0) - g * oi * 100 * spot

        except Exception:
            continue

    return spot, info, gex_by_strike

def get_key_gex_levels(spot, gex_by_strike):
    if not gex_by_strike:
        return None, None, None

    strikes = sorted(gex_by_strike.keys())
    gex_vals = [gex_by_strike[k] for k in strikes]

    # Call wall = strike with highest positive GEX above spot
    above = {k: v for k, v in gex_by_strike.items() if k >= spot and v > 0}
    call_wall = max(above, key=above.get) if above else None

    # Put wall = strike with most negative GEX below spot
    below = {k: v for k, v in gex_by_strike.items() if k <= spot and v < 0}
    put_wall = min(below, key=below.get) if below else None

    # Gamma flip = zero-crossing closest to spot
    flip = None
    min_dist = float('inf')
    for i in range(len(strikes) - 1):
        v1, v2 = gex_by_strike[strikes[i]], gex_by_strike[strikes[i + 1]]
        if v1 * v2 < 0:
            # linear interpolation of zero crossing
            zero = strikes[i] + abs(v1) / (abs(v1) + abs(v2)) * (strikes[i + 1] - strikes[i])
            dist = abs(zero - spot)
            if dist < min_dist:
                min_dist = dist
                flip = round(zero, 2)

    return call_wall, put_wall, flip

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

# ====================== SIDEBAR ======================
if st.sidebar.button("🔄 Refresh All Market Data"):
    st.cache_data.clear()
    st.rerun()

min_score = st.sidebar.slider("Minimum Score", 0.0, 10.0, 6.5, 0.1)
show_strong_only = st.sidebar.checkbox("Show Only Strong Buy / Buy Call", value=True)

# ====================== TABS ======================
tab1, tab2, tab3 = st.tabs(["📊 Scanner", "📡 GEX Analyzer", "🛎️ Telegram Alerts"])

# ---- Scanner Tab ----
with tab1:
    df_scanner = get_options_scanner()
    df_filtered = df_scanner[df_scanner["Score"] >= min_score].copy()
    if show_strong_only:
        df_filtered = df_filtered[df_filtered["Readiness"].str.contains("Strong|Buy Call", regex=True)]

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

# ---- GEX Analyzer Tab ----
with tab2:
    st.subheader("📡 Gamma Exposure (GEX) Analyzer")
    st.caption("Dealer gamma positioning by strike — computed from live option chains via Black-Scholes. Refreshes every 5 min.")

    GEX_TICKERS = [
        "SPY","QQQ","SPX","AAPL","MSFT","NVDA","TSLA","META","AMZN","GOOGL",
        "AMD","PLTR","HOOD","COIN","SMCI","AVGO","MU","NFLX","LLY","MSTR"
    ]

    col_a, col_b = st.columns([2, 1])
    with col_a:
        gex_ticker = st.selectbox("Select Ticker", GEX_TICKERS, index=0)
    with col_b:
        strike_range_pct = st.slider("Strike range around spot (%)", 5, 30, 15)

    with st.spinner(f"Loading GEX for {gex_ticker}..."):
        spot, info, gex_data = compute_gex(gex_ticker)

    if not gex_data or spot is None:
        st.error(f"Could not load options data for {gex_ticker}.")
    else:
        call_wall, put_wall, gamma_flip = get_key_gex_levels(spot, gex_data)

        # Filter strikes to ±range% around spot
        lo = spot * (1 - strike_range_pct / 100)
        hi = spot * (1 + strike_range_pct / 100)
        filtered = {k: v for k, v in gex_data.items() if lo <= k <= hi}

        if not filtered:
            st.warning("No option data in the selected strike range.")
        else:
            strikes = sorted(filtered.keys())
            gex_vals = [filtered[k] / 1_000_000 for k in strikes]  # scale to $M

            colors = ["#26c6da" if v >= 0 else "#ef5350" for v in gex_vals]

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=strikes,
                y=gex_vals,
                marker_color=colors,
                name="GEX ($M)",
                hovertemplate="Strike: $%{x}<br>GEX: $%{y:.2f}M<extra></extra>"
            ))

            # Spot line
            fig.add_vline(x=spot, line_dash="solid", line_color="white", line_width=2,
                          annotation_text=f"Spot ${spot:.2f}", annotation_position="top left",
                          annotation_font_color="white")

            # Key levels
            if call_wall:
                fig.add_vline(x=call_wall, line_dash="dash", line_color="#66bb6a", line_width=1.5,
                              annotation_text=f"Call Wall ${call_wall}", annotation_position="top right",
                              annotation_font_color="#66bb6a")
            if put_wall:
                fig.add_vline(x=put_wall, line_dash="dash", line_color="#ef9a9a", line_width=1.5,
                              annotation_text=f"Put Wall ${put_wall}", annotation_position="bottom left",
                              annotation_font_color="#ef9a9a")
            if gamma_flip:
                fig.add_vline(x=gamma_flip, line_dash="dot", line_color="#ffd54f", line_width=1.5,
                              annotation_text=f"Flip ${gamma_flip}", annotation_position="top",
                              annotation_font_color="#ffd54f")

            fig.update_layout(
                title=f"{gex_ticker} — Gamma Exposure by Strike",
                xaxis_title="Strike Price",
                yaxis_title="Net GEX ($ Millions)",
                plot_bgcolor="#0e1117",
                paper_bgcolor="#0e1117",
                font_color="white",
                bargap=0.1,
                height=500,
                showlegend=False,
            )
            fig.add_hline(y=0, line_color="gray", line_width=0.8)

            st.plotly_chart(fig, use_container_width=True)

            # Key levels cards
            st.markdown("### Key Levels")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Spot Price", f"${spot:.2f}")
            c2.metric("📗 Call Wall", f"${call_wall}" if call_wall else "—",
                      help="Strongest dealer resistance above spot — price often stalls here")
            c3.metric("📕 Put Wall", f"${put_wall}" if put_wall else "—",
                      help="Strongest dealer support below spot — price often bounces here")
            c4.metric("⚡ Gamma Flip", f"${gamma_flip}" if gamma_flip else "—",
                      help="Above this level: dealers buy rallies (stable). Below: dealers sell dips (volatile).")

            # Regime indicator
            st.markdown("### Market Regime")
            if gamma_flip:
                if spot > gamma_flip:
                    st.success(f"**Positive Gamma Regime** — Spot (${spot:.2f}) is ABOVE the Gamma Flip (${gamma_flip}). Dealers are long gamma: they BUY dips and SELL rips → dampens volatility.")
                else:
                    st.error(f"**Negative Gamma Regime** — Spot (${spot:.2f}) is BELOW the Gamma Flip (${gamma_flip}). Dealers are short gamma: they SELL dips and BUY rips → amplifies moves.")
            else:
                st.info("Gamma flip level could not be determined from available data.")

            with st.expander("📖 How to read this chart"):
                st.markdown("""
                **Blue bars (positive GEX):** Dealers are net long gamma here — they hedge by selling as price rises and buying as price falls. Acts as a **magnet / resistance ceiling**.

                **Red bars (negative GEX):** Dealers are net short gamma here — they hedge by buying as price rises and selling as price falls. Acts as a **volatility accelerant**.

                **Call Wall (green dashed):** Highest positive GEX strike above spot — strongest structural resistance.

                **Put Wall (red dashed):** Most negative GEX strike below spot — strongest structural support.

                **Gamma Flip (yellow dotted):** The price level where net GEX crosses zero. Above = stable/range-bound; below = volatile/trending.

                *Data source: yfinance option chains + Black-Scholes gamma computation. Refreshes every 5 minutes.*
                """)

# ---- Telegram Tab ----
with tab3:
    st.subheader("🛎️ Telegram Alerts")
    if st.button("📤 Send Test Telegram Alert", type="primary"):
        msg = f"🧪 Test Alert from Call Buying Pro\nTime: {datetime.now().strftime('%H:%M')}"
        if send_telegram_alert(msg):
            st.success("✅ Sent to Telegram!")
        else:
            st.error("Telegram not configured")

st.divider()
st.caption("✅ Scanner + GEX Analyzer + Telegram Alerts")
