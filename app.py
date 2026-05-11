import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="Call Buying Pro Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("🚀 Call Buying Readiness Pro")
st.caption(f"Last Updated: {datetime.now().strftime('%b %d, %Y %H:%M')} | Live Options Flow + Scoring")

# ====================== SIDEBAR ======================
st.sidebar.header("🎛️ Controls")
refresh_btn = st.sidebar.button("🔄 Refresh All Data (Live)")

watchlist = st.sidebar.multiselect(
    "Your Permanent Watchlist",
    ["MSFT", "META", "NFLX", "LLY", "CVX", "XOM", "MU", "CVNA", "INTC", "TSLA", "NVDA", "AAPL"],
    default=["MSFT", "META", "NFLX", "MU", "CVNA"]
)

min_score = st.sidebar.slider("Minimum Score Filter", 0.0, 10.0, 6.5, 0.1)
show_only_strong = st.sidebar.checkbox("Show Only Strong Buy Call", value=True)

# ====================== SAMPLE DATA (Replace with real API later) ======================
data = {
    "Ticker": ["NFLX", "MU", "CVNA", "META", "INTC", "TSLA", "MSFT", "LLY"],
    "Price": [87.4, 798.5, 287.2, 609.8, 126.4, 428.1, 412.7, 962.3],
    "Score": [8.6, 8.7, 8.1, 7.6, 7.5, 6.9, 5.4, 6.4],
    "IV_Rank": [26, 42, 35, 31, 52, 68, 71, 48],
    "Days_to_Earnings": [66, 42, 28, 78, 19, 35, 78, 55],
    "Support_Dist_Pct": [1.2, 3.5, -0.8, 2.1, 4.0, -1.5, 0.8, 0.5],
    "Readiness": ["Strong Buy Call", "Strong Buy Call", "Strong Buy Call", "Buy Call", "Buy Call", "Monitor", "Neutral", "Monitor"],
    "Latest_Flow": ["Near support + low IV", "$1000C Jun heavy sweeps", "$915K repeat calls", "Bullish momentum", "Aggressive May 15 calls", "Mixed but strong calls", "Elevated IV repeats", "Quiet"],
    "Risk_1_Contract": [450, 1200, 850, 1800, 650, 950, 1250, 3400]
}

df = pd.DataFrame(data)
df_filtered = df[df["Score"] >= min_score]
if show_only_strong:
    df_filtered = df_filtered[df_filtered["Readiness"].str.contains("Strong Buy|Buy Call")]

# ====================== MAIN LAYOUT ======================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Main Scanner", "📈 Charts", "💰 1-Contract Simulator", "🔍 X Flow Signals", "⚙️ Settings"])

with tab1:
    st.subheader("Strong Buy Call Candidates")
    st.dataframe(
        df_filtered.style.background_gradient(subset=["Score"], cmap="RdYlGn")
                         .format({"Score": "{:.1f}", "Support_Dist_Pct": "{:.1f}%"}),
        use_container_width=True,
        height=500
    )
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Strong Buy Signals", len(df_filtered[df_filtered["Readiness"].str.contains("Strong Buy Call")]))
    with col2:
        st.metric("Total Capital at Risk (1 contract each)", f"${df_filtered['Risk_1_Contract'].sum():,}")

with tab2:
    st.subheader("Readiness Score Distribution")
    fig = px.bar(df, x="Ticker", y="Score", color="Readiness", title="Call Buying Scores", height=450)
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("IV Rank vs Score")
    fig2 = px.scatter(df, x="IV_Rank", y="Score", color="Ticker", size="Days_to_Earnings",
                      hover_data=["Latest_Flow"], title="Lower IV Rank = Better Opportunity")
    st.plotly_chart(fig2, use_container_width=True)

with tab3:
    st.subheader("1-Contract Simulator")
    selected = st.selectbox("Select Ticker to Simulate", df["Ticker"])
    contracts = st.slider("Number of Contracts", 1, 20, 1)
    
    row = df[df["Ticker"] == selected].iloc[0]
    
    st.write(f"**{selected}** — Score: {row['Score']}/10 | Current Price: ${row['Price']:,}")
    
    premium = row['Risk_1_Contract'] / 100
    total_cost = premium * 100 * contracts
    breakeven = row['Price'] * 1.06  # example 6% OTM + premium
    
    st.metric("Total Cost", f"${total_cost:,.0f}")
    st.metric("Breakeven Price", f"${breakeven:.2f}")
    
    upside = st.slider("Expected Stock Move %", 0, 50, 15)
    profit = total_cost * (upside / 15) * 0.8  # simplified model
    
    st.success(f"Potential Profit at {upside}% move: **${profit:,.0f}** (+{profit/total_cost*100:.0f}%)")
    st.warning(f"Max Loss: **-${total_cost:,.0f}**")

with tab4:
    st.subheader("Latest X Options Flow Signals")
    st.info("🔴 Live signals from @unusual_whales, @OptionsHawk, @baalhadid etc. would appear here.")
    
    # Placeholder for real signals
    signals = pd.DataFrame({
        "Ticker": ["MU", "CVNA", "NFLX"],
        "Signal": ["Heavy $1000C Jun sweeps ($1.2M)", "$915K repeat calls", "Bullish flow near support"],
        "Source": ["@DarkFlowAlert", "@baalhadid", "@unusual_whales"],
        "Time": ["2h ago", "5h ago", "Yesterday"]
    })
    st.dataframe(signals, use_container_width=True)

with tab5:
    st.subheader("Dashboard Settings")
    st.write("You can expand this with API keys, scoring weights, alert rules, etc.")
    st.checkbox("Enable Dark Mode", value=True)
    st.selectbox("Default Expiry Focus", ["45-90 DTE", "30-60 DTE", "0-7 DTE"])

# ====================== FOOTER ======================
st.divider()
st.caption("💡 Pro Tips: Refresh often • Click rows in tables for deeper dives • We can connect real Polygon.io + X scraping next")
