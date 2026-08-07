"""
Synthetic data generator.

Real PMS / booking data is proprietary, so this module generates a plausible
demo dataset for one hotel with several room types: a demand pattern with
weekly (weekend) and monthly seasonality, occasional event-driven demand
spikes, and a matching booking-pace signal. This stands in for the
Data Ingestion & Feature Store layer described in the Day 1 design doc.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

ROOM_TYPES = [
    {"name": "Standard Queen", "base_rate": 120, "capacity": 40},
    {"name": "Deluxe King", "base_rate": 165, "capacity": 25},
    {"name": "Suite", "base_rate": 260, "capacity": 10},
]

HOTEL_NAME = "Demo Hotel — Lakeside Business District"
TOTAL_ROOMS = sum(rt["capacity"] for rt in ROOM_TYPES)


def _demand_index(day_offset: int, seed_shift: float, rng: np.random.Generator) -> float:
    """Underlying 0-100 demand index for a given day offset from today."""
    dow_component = 18 * np.sin((day_offset / 7) * 2 * np.pi + 1.2)  # weekly (weekend) pattern
    month_component = 14 * np.sin((day_offset / 30) * 2 * np.pi * 1.1 + seed_shift)
    trend = 55
    noise = rng.normal(0, 3.5)
    # occasional event spike (~1 in 12 days)
    spike = 22 if rng.random() < 0.08 else 0
    return float(np.clip(trend + dow_component + month_component + noise + spike, 8, 100))


def generate_daily_metrics(
    horizon_days: int = 90,
    history_days: int = 60,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Returns a per-date, per-room-type feature table covering `history_days`
    of the past (for pace/forecast context) through `horizon_days` of the
    future (the pricing horizon), matching the DailyMetrics entity in the
    Day 1 database design.
    """
    rng = np.random.default_rng(seed)
    today = date.today()
    start = today - timedelta(days=history_days)
    end = today + timedelta(days=horizon_days)
    dates = pd.date_range(start, end, freq="D")

    rows = []
    for rt_idx, rt in enumerate(ROOM_TYPES):
        seed_shift = rt_idx * 0.7
        for d in dates:
            offset = (d.date() - today).days
            demand = _demand_index(offset, seed_shift, rng)

            # Occupancy pace vs. "last year" for the same date (synthetic comparator)
            occ_pace = np.clip((demand - 55) * 0.9 + rng.normal(0, 4), -35, 45)

            # Competitor average rate: correlated with demand, plus noise
            competitor_rate = rt["base_rate"] * (0.92 + 0.35 * (demand / 100)) * (1 + rng.normal(0, 0.04))

            # Historical occupancy actuals only make sense for past dates
            if offset <= 0:
                occupancy_pct = float(np.clip((demand / 100) * 0.95 + rng.normal(0, 0.03), 0.05, 0.99))
                avg_rate = rt["base_rate"] * (0.9 + 0.3 * (demand / 100))
            else:
                occupancy_pct = np.nan
                avg_rate = np.nan

            rows.append({
                "date": d.date(),
                "room_type": rt["name"],
                "base_rate": rt["base_rate"],
                "capacity": rt["capacity"],
                "demand_score": round(demand, 2),
                "occupancy_pace_pct": round(occ_pace, 2),
                "competitor_avg_rate": round(float(competitor_rate), 2),
                "days_to_arrival": max(offset, 0),
                "is_future": offset > 0,
                "occupancy_pct": None if np.isnan(occupancy_pct) else round(occupancy_pct, 3),
                "avg_rate": None if np.isnan(avg_rate) else round(float(avg_rate), 2),
                "day_of_week": d.strftime("%A"),
            })

    return pd.DataFrame(rows)


def get_room_types() -> list[dict]:
    return ROOM_TYPES
