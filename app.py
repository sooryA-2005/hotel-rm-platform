"""
Hotel Revenue Management & Dynamic Pricing Platform — Streamlit demo.

Implements the pipeline from the Day 1 design doc end to end:
  Ingest (data_gen) -> Forecast (forecast) -> Optimize + Explain (pricing_engine)
  -> Dashboard (this file): rate calendar, what-if simulator, RevPAR comparison.

Run locally:  streamlit run app.py
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import data_gen, forecast, pricing_engine

st.set_page_config(
    page_title="Hotel Revenue Management & Dynamic Pricing",
    page_icon="🏨",
    layout="wide",
)

NAVY = "#1f3a5f"
TEAL = "#2a9d8f"
CORAL = "#e76f51"
GREY = "#8d99ae"


# ---------------------------------------------------------------------------
# Data pipeline (cached so the app stays snappy while navigating tabs)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_pipeline(seed: int, horizon_days: int, history_days: int) -> pd.DataFrame:
    raw = data_gen.generate_daily_metrics(horizon_days=horizon_days, history_days=history_days, seed=seed)
    fc = forecast.forecast_demand(raw)
    rec = pricing_engine.compute_recommendations(fc)
    return rec


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🏨 Controls")
    st.caption(data_gen.HOTEL_NAME)
    horizon = st.slider("Pricing horizon (days)", 30, 120, 60, step=15)
    history = st.slider("Historical lookback (days)", 30, 120, 60, step=15)
    seed = st.number_input("Data seed", value=42, step=1, help="Change to regenerate a different synthetic demand pattern.")
    st.divider()
    st.caption(
        "All data on this page is **synthetically generated** for demo purposes "
        "— see the Day 1 design doc's Assumptions & Constraints for why."
    )

rec_df = load_pipeline(seed, horizon, history)
room_types = [rt["name"] for rt in data_gen.get_room_types()]

st.title("Hotel Revenue Management & Dynamic Pricing Platform")
st.caption(f"{data_gen.HOTEL_NAME}  ·  {data_gen.TOTAL_ROOMS} total rooms across {len(room_types)} room types")

tab_calendar, tab_simulator, tab_revpar, tab_forecast = st.tabs(
    ["📅 Rate Calendar", "🧮 What-If Simulator", "📈 RevPAR Comparison", "🔍 Forecast & Model"]
)

# ---------------------------------------------------------------------------
# Tab 1: Rate calendar heatmap
# ---------------------------------------------------------------------------
with tab_calendar:
    st.subheader("Recommended Rates — Rate Calendar")
    room_pick = st.selectbox("Room type", room_types, key="cal_room")
    future = rec_df[(rec_df["room_type"] == room_pick) & (rec_df["is_future"])].copy()
    future["date"] = pd.to_datetime(future["date"])
    future["week"] = future["date"].dt.isocalendar().week
    future["dow"] = future["date"].dt.day_name()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Avg. recommended rate", f"${future['recommended_rate'].mean():,.0f}")
    col2.metric("Base rate", f"${future['base_rate'].iloc[0]:,.0f}")
    col3.metric("Max multiplier hit", f"{future['applied_multiplier'].max():.2f}×")
    col4.metric("Min multiplier hit", f"{future['applied_multiplier'].min():.2f}×")

    fig = px.density_heatmap(
        future, x="date", y=[""] * len(future), z="recommended_rate",
        histfunc="avg", nbinsx=len(future),
        color_continuous_scale=[GREY, TEAL, CORAL],
        labels={"z": "Recommended rate ($)"},
    )
    fig.update_layout(height=180, yaxis_visible=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=future["date"], y=future["base_rate"], name="Base rate",
                               line=dict(color=GREY, dash="dot")))
    fig2.add_trace(go.Scatter(x=future["date"], y=future["recommended_rate"], name="Recommended rate",
                               line=dict(color=TEAL, width=3)))
    fig2.update_layout(height=380, margin=dict(t=20, b=10), yaxis_title="Rate ($)",
                        legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("**Why these prices? (Explainability Layer)**")
    show_cols = ["date", "recommended_rate", "applied_multiplier", "forecast_demand_score",
                 "occupancy_pace_pct", "confidence", "reasoning"]
    display = future[show_cols].rename(columns={
        "date": "Date", "recommended_rate": "Rate ($)", "applied_multiplier": "Multiplier",
        "forecast_demand_score": "Demand score", "occupancy_pace_pct": "Pace (%)",
        "confidence": "Source", "reasoning": "Reason",
    })
    display["Date"] = display["Date"].dt.strftime("%a, %b %d")
    st.dataframe(display, use_container_width=True, hide_index=True, height=320)

# ---------------------------------------------------------------------------
# Tab 2: What-if simulator
# ---------------------------------------------------------------------------
with tab_simulator:
    st.subheader("What-If Price Simulator")
    st.caption("Pick a date and room type, then drag the price slider to see the projected occupancy and revenue impact.")

    c1, c2 = st.columns(2)
    sim_room = c1.selectbox("Room type", room_types, key="sim_room")
    sim_future = rec_df[(rec_df["room_type"] == sim_room) & (rec_df["is_future"])].copy()
    sim_future["date"] = pd.to_datetime(sim_future["date"])
    date_options = sim_future["date"].dt.strftime("%a, %b %d, %Y").tolist()
    sim_date_label = c2.selectbox("Date", date_options, key="sim_date")
    row = sim_future.iloc[date_options.index(sim_date_label)]

    base_rate = float(row["base_rate"])
    rec_rate = float(row["recommended_rate"])
    min_p, max_p = base_rate * pricing_engine.MIN_MULTIPLIER * 0.8, base_rate * pricing_engine.MAX_MULTIPLIER * 1.15

    price = st.slider(
        "Hypothetical price ($)", min_value=float(round(min_p)), max_value=float(round(max_p)),
        value=float(round(rec_rate)), step=1.0,
    )

    projection = pricing_engine.what_if(row, price)
    rec_projection = pricing_engine.what_if(row, rec_rate)
    static_projection = pricing_engine.what_if(row, base_rate)

    m1, m2, m3 = st.columns(3)
    m1.metric("Projected occupancy", f"{projection['projected_occupancy_pct']}%")
    m2.metric("Projected rooms sold", f"{projection['projected_rooms_sold']} / {row['capacity']}")
    m3.metric("Projected revenue", f"${projection['projected_revenue']:,.0f}")

    st.markdown("**Comparison at this date**")
    comp = pd.DataFrame([
        {"Scenario": "Static (base rate)", "Price": base_rate, "Occupancy %": static_projection["projected_occupancy_pct"], "Revenue": static_projection["projected_revenue"]},
        {"Scenario": "Engine recommendation", "Price": rec_rate, "Occupancy %": rec_projection["projected_occupancy_pct"], "Revenue": rec_projection["projected_revenue"]},
        {"Scenario": "Your hypothetical price", "Price": price, "Occupancy %": projection["projected_occupancy_pct"], "Revenue": projection["projected_revenue"]},
    ])
    fig3 = px.bar(comp, x="Scenario", y="Revenue", color="Scenario",
                  color_discrete_sequence=[GREY, TEAL, CORAL], text="Revenue")
    fig3.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
    fig3.update_layout(height=380, showlegend=False, margin=dict(t=20, b=10))
    st.plotly_chart(fig3, use_container_width=True)
    st.dataframe(comp.style.format({"Price": "${:.0f}", "Revenue": "${:,.0f}"}), use_container_width=True, hide_index=True)

    st.info(f"**Engine's stated reasoning for this date:** {row['reasoning']}")

# ---------------------------------------------------------------------------
# Tab 3: RevPAR comparison
# ---------------------------------------------------------------------------
with tab_revpar:
    st.subheader("RevPAR: Static vs. Dynamic Pricing")
    revpar_room = st.selectbox("Room type", ["All room types"] + room_types, key="revpar_room")

    sim_all = pricing_engine.simulate_static_vs_dynamic(rec_df)
    if revpar_room != "All room types":
        sim_all = sim_all[sim_all["room_type"] == revpar_room]

    sim_all["date"] = pd.to_datetime(sim_all["date"])
    daily = sim_all.groupby("date").agg(
        static_revenue=("static_revenue", "sum"),
        dynamic_revenue=("dynamic_revenue", "sum"),
        capacity=("capacity", "sum"),
    ).reset_index()
    daily["static_revpar"] = daily["static_revenue"] / daily["capacity"]
    daily["dynamic_revpar"] = daily["dynamic_revenue"] / daily["capacity"]
    daily["cum_static"] = daily["static_revenue"].cumsum()
    daily["cum_dynamic"] = daily["dynamic_revenue"].cumsum()

    total_static = daily["static_revenue"].sum()
    total_dynamic = daily["dynamic_revenue"].sum()
    lift_pct = (total_dynamic - total_static) / total_static * 100 if total_static else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("Static revenue (horizon)", f"${total_static:,.0f}")
    m2.metric("Dynamic revenue (horizon)", f"${total_dynamic:,.0f}")
    m3.metric("Revenue lift", f"{lift_pct:+.1f}%")

    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=daily["date"], y=daily["cum_static"], name="Static pricing",
                               line=dict(color=GREY, width=2.5)))
    fig4.add_trace(go.Scatter(x=daily["date"], y=daily["cum_dynamic"], name="Dynamic pricing",
                               line=dict(color=TEAL, width=2.5), fill="tonexty",
                               fillcolor="rgba(42,157,143,0.08)"))
    fig4.update_layout(height=420, yaxis_title="Cumulative revenue ($)", margin=dict(t=20, b=10),
                        legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig4, use_container_width=True)

    fig5 = px.line(daily, x="date", y=["static_revpar", "dynamic_revpar"],
                    color_discrete_sequence=[GREY, CORAL],
                    labels={"value": "RevPAR ($)", "date": "Date", "variable": "Scenario"})
    fig5.update_layout(height=360, margin=dict(t=20, b=10), legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig5, use_container_width=True)

    st.caption(
        "Simulation uses a capacity-constrained elasticity model (demand saturates below a "
        "threshold price, then becomes price-elastic above it) — see the Technical Analysis "
        "report for the underlying assumptions. Figures are illustrative, not a guaranteed result."
    )

# ---------------------------------------------------------------------------
# Tab 4: Forecast & model internals
# ---------------------------------------------------------------------------
with tab_forecast:
    st.subheader("Demand Forecast & Model Internals")
    fc_room = st.selectbox("Room type", room_types, key="fc_room")
    fc_df = rec_df[rec_df["room_type"] == fc_room].copy()
    fc_df["date"] = pd.to_datetime(fc_df["date"])

    source = fc_df["forecast_source"].iloc[0]
    st.write(f"**Forecast source:** `{source}`  "
             f"({'gradient-boosted regressor trained on historical rows' if source == 'gradient_boosting' else 'rule-based fallback (insufficient history to train)'})")

    fig6 = go.Figure()
    fig6.add_trace(go.Scatter(x=fc_df["date"], y=fc_df["demand_score"], name="Raw demand signal",
                               line=dict(color=GREY, dash="dot")))
    fig6.add_trace(go.Scatter(x=fc_df["date"], y=fc_df["forecast_demand_score"], name="Forecasted demand score",
                               line=dict(color=NAVY, width=2.5)))
    fig6.add_vline(x=pd.Timestamp.today(), line_dash="dash", line_color=CORAL,
                    annotation_text="today", annotation_position="top")
    fig6.update_layout(height=380, yaxis_title="Demand score (0-100)", margin=dict(t=20, b=10),
                        legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig6, use_container_width=True)

    st.markdown("**Price multiplier vs. occupancy pace & lead time** (guardrails applied)")
    fig7 = px.scatter(
        fc_df[fc_df["is_future"]], x="occupancy_pace_pct", y="days_to_arrival",
        color="applied_multiplier", size="forecast_demand_score",
        color_continuous_scale=[TEAL, "#f2e9c7", CORAL],
        labels={"occupancy_pace_pct": "Occupancy pace (%)", "days_to_arrival": "Days to arrival",
                "applied_multiplier": "Multiplier"},
    )
    fig7.update_layout(height=420, margin=dict(t=20, b=10))
    st.plotly_chart(fig7, use_container_width=True)

    with st.expander("Guardrail configuration (Price Optimization Engine)"):
        st.write(f"- Minimum multiplier: **{pricing_engine.MIN_MULTIPLIER}×** base rate")
        st.write(f"- Maximum multiplier: **{pricing_engine.MAX_MULTIPLIER}×** base rate")
        st.write(f"- Maximum day-over-day change: **{pricing_engine.MAX_DAILY_CHANGE * 100:.0f}%**")
        st.caption("These bounds are enforced in `src/pricing_engine.py`, independent of the UI, per the Technical Design Document.")

st.divider()
st.caption(
    "Reference implementation of the Day 1 architecture: Ingest → Store → Forecast → "
    "Optimize → Explain → Publish. Built with Streamlit · scikit-learn · Plotly."
)
