import streamlit as st
import pandas as pd
from datetime import datetime

# Try to import Plotly with fallback
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.warning("⚠️ Plotly not available. Charts will be disabled.")

st.set_page_config(page_title="Call Buying Pro", layout="wide", initial_sidebar_state="expanded")

st.title("🚀 Call Buying Readiness Pro")
st.caption(f"Last Updated: {datetime.now().strftime('%b %d, %Y %H:%M')} | Options Flow + Scoring Engine")

# ====================== SIDEBAR ======================
st.sidebar.header("🎛️ Controls")
if st.sidebar.button("🔄 Refresh All Data"):
    st.rerun()

watchlist = st.sidebar.multiselect(
    "Permanent Watchlist",
    ["MSFT", "META", "NFLX", "LLY", "CVX", "XOM", "MU", "CVNA", "INTC", "TSLA", "NVDA", "AAPL"],
    default=["MSFT", "META", "NFLX", "MU", "CVNA"]
)

min_score = st.sidebar.slider("Minimum Score", 0.0, 10.0, 6.5, 0.1)
show_strong_only = st.sidebar.checkbox("Show Only Strong Buy / Buy Call", value=True)

# ====================== DATA ======================
data = {
    "Ticker": ["NFLX", "MU", "CVNA", "META", "INTC", "TSLA", "MSFT", "LLY"],
    "Price": [87.4, 798.5, 287.2, 609.8, 126.4, 428.1, 412.7, 962.3],
    "Score": [8.6, 8.7, 8.1, 7.6, 7.5, 6.9, 5.4, 6.4],
    "IV_Rank": [26, 42, 35, 31, 52, 68, 71, 48],
    "Days_to_Earnings": [66, 42, 28, 78, 19, 35, 78, 55],
    "Readiness": ["Strong Buy Call", "Strong Buy Call", "Strong Buy Call", "Buy Call", "Buy Call", "Monitor", "Neutral", "Monitor"],
    "Latest_Flow": ["Low IV + near support", "Heavy $1000C Jun sweeps", "$915K repeat calls", "Strong momentum", "Aggressive May calls", "Mixed strong calls", "High IV Rank", "Quiet"],
    "Risk_1_Contract": [450, 1250, 850, 1800, 650, 950, 1250, 3400]
}

df = pd.DataFrame(data)
df_filtered = df[df["Score"] >= min_score].copy()

if show_strong_only:
    df_filtered = df_filtered[df_filtered["Readiness"].str.contains("Strong Buy|Buy Call")]

# ====================== TABS ======================
tab1, tab2, tab3, tab4 = st.tabs(["📊 Scanner", "📈 Charts", "💰 Simulator", "🔍 X Flow"])

with tab1:
    st.subheader("Strong Buy Call Candidates")
    st.dataframe(
        df_filtered.style.background_gradient(subset=["Score"], cmap="RdYlGn")
                         .format({"Score": "{:.1f}"}),
        use_container_width=True,
        height=480
    )
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Strong Buy", len(df_filtered[df_filtered["Readiness"] == "Strong Buy Call"]))
    with col2:
        st.metric("Buy Call", len(df_filtered[df_filtered["Readiness"] == "Buy Call"]))
    with col3:
        st.metric("Total Risk (1 contract each)", f"${df_filtered['Risk_1_Contract'].sum():,}")

with tab2:
    st.subheader("Readiness Score Distribution")
    if PLOTLY_AVAILABLE:
        fig = px.bar(df, x="Ticker", y="Score", color="Readiness", title="Call Buying Scores")
        st.plotly_chart(fig, use_container_width=True)
        
        fig2 = px.scatter(df, x="IV_Rank", y="Score", color="Ticker", size="Days_to_Earnings",
                          title="Lower IV Rank = Better Setup", hover_data=["Latest_Flow"])
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Charts disabled — Plotly not installed.")

with tab3:
    st.subheader("1-Contract Simulator")
    selected = st.selectbox("Select Ticker", df["Ticker"])
    contracts = st.slider("Number of Contracts", 1, 20, 1)
    
    row = df[df["Ticker"] == selected].iloc[0]
    
    premium = row['Risk_1_Contract']
    total_cost = premium * contracts
    
    st.metric("Total Cost for {} contract(s)".format(contracts), f"${total_cost:,}")
    st.metric("Est. Breakeven", f"${row['Price'] * 1.07:.2f} (approx)")
    
    upside = st.slider("Expected Upside Move (%)", 5, 60, 20)
    est_profit = int(total_cost * (upside / 20))
    
    st.success(f"**Potential Profit**: ${est_profit:,} (+{upside}%)")
    st.warning(f"**Max Loss**: -${total_cost:,}")

with tab4:
    st.subheader("Latest Options Flow from X")
    st.info("This section can be connected to real X signals later.")
    signals = pd.DataFrame({
        "Ticker": ["MU", "CVNA", "NFLX"],
        "Flow": ["Heavy bullish sweeps $1000C", "$915K repeat call buying", "Support + low IV flow"],
        "Source": ["@unusual_whales / @DarkFlowAlert", "@baalhadid", "Our scanner"],
        "Time": ["2 hours ago", "Today", "Yesterday"]
    })
    st.dataframe(signals, use_container_width=True)

st.divider()
st.caption("💡 Tip: Add requirements.txt with: streamlit, pandas, plotly | Refresh often | We can add live Polygon data next")
