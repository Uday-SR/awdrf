"""Core logic: which forecast was available at decision time, and how accurate was it?"""
import numpy as np
import pandas as pd

LONDON = "Europe/London"
HALF_HOUR_H = 0.5  # MW * 0.5h = MWh


def parse_cutoff(cutoff: str):
    try:
        h, m = (int(x) for x in cutoff.split(":"))
        assert 0 <= h < 24 and 0 <= m < 60
        return h, m
    except Exception as exc:
        raise ValueError("cutoff must be HH:MM (UK local time)") from exc


def decision_forecasts(raw: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    """For every target half-hour on day D keep the latest forecast published at or
    before `cutoff` (UK local time) on day D-1."""
    h, m = parse_cutoff(cutoff)
    df = raw.copy()
    local_day = df["startTime"].dt.tz_convert(LONDON).dt.tz_localize(None).dt.normalize()
    cut = local_day - pd.Timedelta(days=1) + pd.Timedelta(hours=h, minutes=m)
    df["cutoff"] = cut.dt.tz_localize(LONDON, ambiguous=True, nonexistent="shift_forward").dt.tz_convert("UTC")
    df = df[df["publishTime"] <= df["cutoff"]]
    df = df.sort_values("publishTime").groupby("startTime", as_index=False).last()
    return df.rename(columns={"generation": "forecast"})


def build_frame(forecasts: pd.DataFrame, actuals: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    fc = decision_forecasts(forecasts, cutoff)
    df = fc.merge(actuals, on="startTime", how="left")
    local = df["startTime"].dt.tz_convert(LONDON)
    df["date"] = local.dt.strftime("%Y-%m-%d")
    df["slot"] = local.dt.strftime("%H:%M")
    df["error"] = df["forecast"] - df["actual"]  # +ve = over-forecast (risk: under-buying)
    return df.sort_values("startTime").reset_index(drop=True)


def metrics(df: pd.DataFrame):
    d = df.dropna(subset=["forecast", "actual"])
    if d.empty:
        return None
    e, ae = d["error"], d["error"].abs()
    nz = d[d["actual"] > 0]
    mae = ae.mean()
    return {
        "n": int(len(d)),
        "mae": mae,
        "rmse": float(np.sqrt((e ** 2).mean())),
        "bias": e.mean(),
        "mape": float((nz["error"].abs() / nz["actual"]).mean() * 100) if len(nz) else None,
        "nmae_pct": float(mae / d["actual"].mean() * 100) if d["actual"].mean() else None,
        "p90_abs_error": ae.quantile(0.9),
        "err_p10": e.quantile(0.1),
        "err_p90": e.quantile(0.9),
        "mean_actual": d["actual"].mean(),
    }


def accuracy(frame: pd.DataFrame):
    d = frame.dropna(subset=["forecast", "actual"])
    daily = [{"date": k, **(metrics(g) or {})} for k, g in d.groupby("date")]
    by_slot = [{"slot": k, **(metrics(g) or {})} for k, g in d.groupby("slot")]
    edges = np.arange(-6000, 6001, 500)
    counts, _ = np.histogram(d["error"].clip(-5999, 5999), bins=edges)
    hist = [{"bin_start": int(edges[i]), "count": int(c)} for i, c in enumerate(counts)]
    return {"overall": metrics(frame), "daily": daily, "by_slot": by_slot, "histogram": hist}


def day_view(frame: pd.DataFrame, day: str, cutoff: str):
    sub = frame[frame["date"] == day]
    if sub.empty:
        return None
    m = metrics(frame) or {}
    q10, q90 = m.get("err_p10", 0.0), m.get("err_p90", 0.0)
    # actual ≈ forecast - error  ->  80% interval from the empirical error quantiles
    lower = (sub["forecast"] - q90).clip(lower=0)
    upper = (sub["forecast"] - q10).clip(lower=0)
    pubs = sorted(sub["publishTime"].unique())
    has_actual = bool(sub["actual"].notna().all())
    f_mwh = float(sub["forecast"].sum() * HALF_HOUR_H)
    lo_mwh = float(lower.sum() * HALF_HOUR_H)
    summary = {
        "forecast_mwh": f_mwh,
        "p10_mwh": lo_mwh,
        "p90_mwh": float(upper.sum() * HALF_HOUR_H),
        "downside_buffer_mwh": f_mwh - lo_mwh,
        "actual_mwh": float(sub["actual"].sum() * HALF_HOUR_H) if has_actual else None,
        "peak_forecast_mw": float(sub["forecast"].max()),
        "min_forecast_mw": float(sub["forecast"].min()),
        "latest_publish_time": pd.Timestamp(pubs[-1]).isoformat(),
        "earliest_publish_time": pd.Timestamp(pubs[0]).isoformat(),
        "cutoff_time": pd.Timestamp(sub["cutoff"].iloc[0]).isoformat(),
        "n_vintages": len(pubs),
        "day_metrics": metrics(sub),
    }
    rows = [
        {"slot": r.slot, "startTime": r.startTime.isoformat(), "forecast": r.forecast,
         "actual": r.actual, "lower": lo, "upper": up, "publishTime": r.publishTime.isoformat()}
        for r, lo, up in zip(sub.itertuples(), lower, upper)
    ]
    return {"date": day, "cutoff": cutoff, "series": rows, "summary": summary}


def clean(o):
    """Make results JSON-safe (NaN -> None, numpy -> python)."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if np.isnan(o) or np.isinf(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o
