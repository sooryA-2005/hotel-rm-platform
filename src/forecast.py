"""
Demand Forecast Model.

Trains a lightweight gradient-boosting regressor on historical (past) rows
to predict the demand_score from calendar and pace features, then scores
every future date/room-type. Falls back to the raw synthetic demand_score
if there isn't enough history to fit a model (e.g., a very short lookback),
which mirrors the "fall back to the rule-based signal" behavior specified
in the Day 1 Technical Design Document's error-handling section.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

FEATURES = ["occupancy_pace_pct", "competitor_avg_rate", "days_to_arrival", "dow_sin", "dow_cos"]


def _add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    dow_num = pd.to_datetime(df["date"]).dt.dayofweek
    df["dow_sin"] = np.sin(2 * np.pi * dow_num / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow_num / 7)
    return df


def forecast_demand(df: pd.DataFrame, min_train_rows: int = 40) -> pd.DataFrame:
    """
    df: output of data_gen.generate_daily_metrics() for a single room type
        (or the full multi-room-type frame; forecasting is done per room type).
    Returns df with an added `forecast_demand_score` column for every row
    (fitted/backfilled for history, predicted for future dates).
    """
    out_frames = []
    for rt, g in df.groupby("room_type"):
        g = _add_calendar_features(g).sort_values("date").reset_index(drop=True)
        train = g[~g["is_future"]]

        if len(train) >= min_train_rows:
            model = GradientBoostingRegressor(
                n_estimators=120, max_depth=3, learning_rate=0.08, random_state=7
            )
            model.fit(train[FEATURES], train["demand_score"])
            g["forecast_demand_score"] = model.predict(g[FEATURES]).clip(0, 100)
            g["forecast_source"] = "gradient_boosting"
        else:
            # Fallback: not enough history to fit a model — use the raw
            # synthetic demand score directly (rule-based fallback path).
            g["forecast_demand_score"] = g["demand_score"]
            g["forecast_source"] = "fallback_rule_based"

        out_frames.append(g)

    return pd.concat(out_frames, ignore_index=True)
