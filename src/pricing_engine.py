"""
Price Optimization Engine + Explainability Layer.

Converts a forecasted demand score into a bounded price recommendation:

    recommended_price = base_rate * price_multiplier(demand_score, pace, lead_time)

price_multiplier is clipped to [MIN_MULTIPLIER, MAX_MULTIPLIER] and the
day-over-day change is rate-limited, per the guardrails specified in the
Day 1 Technical Design Document. Every recommendation carries a short,
human-readable reason code (the Explainability Layer module).
"""

import numpy as np
import pandas as pd

MIN_MULTIPLIER = 0.75
MAX_MULTIPLIER = 1.70
MAX_DAILY_CHANGE = 0.12  # max 12% change vs. previous day's recommended price


def _raw_multiplier(demand_score: float, occupancy_pace_pct: float, days_to_arrival: int) -> float:
    """Rule-based multiplier surface (occupancy pace x lead time x demand)."""
    demand_component = 0.012 * (demand_score - 55)
    pace_component = 0.006 * occupancy_pace_pct
    urgency_component = -0.004 * (days_to_arrival - 20)
    return 1.0 + demand_component + pace_component + urgency_component


def _reason_code(demand_score, pace, lead_time, multiplier) -> str:
    parts = []
    if pace > 15:
        parts.append(f"occupancy pace is {pace:.0f}% ahead of comparable dates")
    elif pace < -15:
        parts.append(f"occupancy pace is {abs(pace):.0f}% behind comparable dates")
    if demand_score > 70:
        parts.append("forecasted demand is high")
    elif demand_score < 35:
        parts.append("forecasted demand is soft")
    if lead_time <= 7:
        parts.append("arrival date is imminent (short lead time)")
    elif lead_time >= 45:
        parts.append("arrival date is distant (long lead time)")

    if not parts:
        return "Price held near base rate — no strong demand signal in either direction."

    direction = "raised" if multiplier > 1.02 else ("lowered" if multiplier < 0.98 else "held near base rate")
    return f"Price {direction} because " + "; ".join(parts) + "."


def compute_recommendations(forecast_df: pd.DataFrame) -> pd.DataFrame:
    """
    forecast_df: output of forecast.forecast_demand(), containing
    forecast_demand_score, occupancy_pace_pct, days_to_arrival, base_rate.
    Returns df with recommended_rate, applied_multiplier, and reasoning.
    """
    out_frames = []
    for rt, g in forecast_df.groupby("room_type"):
        g = g.sort_values("date").reset_index(drop=True)
        raw_mult = g.apply(
            lambda r: _raw_multiplier(r["forecast_demand_score"], r["occupancy_pace_pct"], r["days_to_arrival"]),
            axis=1,
        )
        bounded_mult = raw_mult.clip(MIN_MULTIPLIER, MAX_MULTIPLIER)

        # Day-over-day rate limiting, applied sequentially over future dates
        limited = bounded_mult.copy()
        future_idx = g.index[g["is_future"]].tolist()
        prev = 1.0
        for i in future_idx:
            lo, hi = prev * (1 - MAX_DAILY_CHANGE), prev * (1 + MAX_DAILY_CHANGE)
            limited.iloc[i] = float(np.clip(bounded_mult.iloc[i], lo, hi))
            prev = limited.iloc[i]

        g["applied_multiplier"] = limited.round(3)
        g["recommended_rate"] = (g["base_rate"] * g["applied_multiplier"]).round(2)
        g["reasoning"] = g.apply(
            lambda r: _reason_code(r["forecast_demand_score"], r["occupancy_pace_pct"], r["days_to_arrival"], r["applied_multiplier"]),
            axis=1,
        )
        g["confidence"] = np.where(g["forecast_source"] == "gradient_boosting", "model-based", "fallback")
        out_frames.append(g)

    return pd.concat(out_frames, ignore_index=True)


def simulate_static_vs_dynamic(rec_df: pd.DataFrame) -> pd.DataFrame:
    """
    Simulated occupancy/revenue comparison for future dates only, following
    the same capacity-constrained elasticity model used in the technical
    analysis report (demand saturates below a threshold price, then becomes
    elastic above it).
    """
    df = rec_df[rec_df["is_future"]].copy()
    elasticity = -1.4

    def occ_for_price(row, price):
        ratio = price / row["base_rate"]
        demand_frac = row["forecast_demand_score"] / 70.0
        uncapped = demand_frac * (ratio ** elasticity)
        return float(np.clip(min(uncapped, 1.0), 0.05, 0.98))

    df["static_occupancy"] = df.apply(lambda r: occ_for_price(r, r["base_rate"]), axis=1)
    df["dynamic_occupancy"] = df.apply(lambda r: occ_for_price(r, r["recommended_rate"]), axis=1)

    df["static_revenue"] = df["static_occupancy"] * df["capacity"] * df["base_rate"]
    df["dynamic_revenue"] = df["dynamic_occupancy"] * df["capacity"] * df["recommended_rate"]

    return df


def what_if(row: pd.Series, hypothetical_price: float) -> dict:
    """Single-date, single-room-type what-if projection used by the simulator page."""
    elasticity = -1.4
    ratio = hypothetical_price / row["base_rate"]
    demand_frac = row["forecast_demand_score"] / 70.0
    occupancy = float(np.clip(min(demand_frac * (ratio ** elasticity), 1.0), 0.05, 0.98))
    revenue = occupancy * row["capacity"] * hypothetical_price
    return {
        "hypothetical_price": hypothetical_price,
        "projected_occupancy_pct": round(occupancy * 100, 1),
        "projected_rooms_sold": round(occupancy * row["capacity"], 1),
        "projected_revenue": round(revenue, 2),
    }
