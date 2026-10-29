import pandas as pd
from app import analysis


def make():
    # Target day 2026-01-02, half-hourly. Two forecast vintages on 01 Jan: 08:00 and 11:00.
    st = pd.date_range("2026-01-02", periods=48, freq="30min", tz="UTC")
    rows = []
    for pub, val in [("2026-01-01T08:00Z", 1000.0), ("2026-01-01T11:00Z", 2000.0)]:
        for s in st:
            rows.append({"publishTime": pd.Timestamp(pub), "startTime": s, "generation": val})
    return pd.DataFrame(rows), pd.DataFrame({"startTime": st, "actual": 900.0})


def test_picks_latest_forecast_before_cutoff():
    fc, ac = make()
    assert (analysis.build_frame(fc, ac, "09:00")["forecast"] == 1000).all()  # 11:00 vintage excluded
    assert (analysis.build_frame(fc, ac, "12:00")["forecast"] == 2000).all()


def test_metrics():
    fc, ac = make()
    m = analysis.metrics(analysis.build_frame(fc, ac, "09:00"))
    assert m["mae"] == 100 and m["bias"] == 100 and m["rmse"] == 100


def test_day_view_and_clean():
    fc, ac = make()
    res = analysis.clean(analysis.day_view(analysis.build_frame(fc, ac, "09:00"), "2026-01-02", "09:00"))
    assert len(res["series"]) == 48 and res["summary"]["forecast_mwh"] == 24000
