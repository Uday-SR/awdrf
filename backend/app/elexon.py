"""Fetch and cache Elexon BMRS data (FUELHH wind actuals, WINDFOR wind forecasts)."""
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

log = logging.getLogger("elexon")

BASE_URL = os.getenv("ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1")
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))

# Target (delivery) month: January 2026. Dates are UTC (== UK local time in January).
TARGET_START = pd.Timestamp("2026-01-01T00:00:00Z")
TARGET_END = pd.Timestamp("2026-02-01T00:00:00Z")
# Forecasts are published ahead of the delivery day, so we need publish times from a
# couple of days before the month starts until the last decision (30 Jan for 31 Jan).
PUBLISH_START = pd.Timestamp("2025-12-30T00:00:00Z")
PUBLISH_END = pd.Timestamp("2026-02-01T00:00:00Z")


def _get_json(path: str, params: dict, retries: int = 3):
    url = f"{BASE_URL}{path}"
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=90, headers={"Accept": "application/json"})
            r.raise_for_status()
            body = r.json()
            return body.get("data", []) if isinstance(body, dict) else body
        except Exception as exc:  # noqa: BLE001
            log.warning("GET %s failed (attempt %d/%d): %s", url, attempt, retries, exc)
            if attempt == retries:
                raise
            time.sleep(2 * attempt)


def _iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_actuals() -> pd.DataFrame:
    """Wind actuals (FUELHH, fuelType=WIND), half-hourly, MW."""
    frames = []
    day = TARGET_START
    while day < TARGET_END:  # 7-day chunks keep us inside API range limits
        end = min(day + pd.Timedelta(days=7), TARGET_END) - pd.Timedelta(days=1)
        rows = _get_json(
            "/datasets/FUELHH/stream",
            {"settlementDateFrom": day.strftime("%Y-%m-%d"),
             "settlementDateTo": end.strftime("%Y-%m-%d"),
             "fuelType": "WIND"},
        )
        frames.append(pd.DataFrame(rows))
        day = end + pd.Timedelta(days=1)
    df = pd.concat(frames, ignore_index=True)
    df = df[df["fuelType"] == "WIND"].copy()
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df = df.rename(columns={"generation": "actual"})[["startTime", "actual"]]
    return df.drop_duplicates("startTime", keep="last").sort_values("startTime").reset_index(drop=True)


def fetch_forecasts() -> pd.DataFrame:
    """All wind forecast vintages (WINDFOR) published in the window, MW."""
    spans, t = [], PUBLISH_START
    while t < PUBLISH_END:
        spans.append((t, min(t + pd.Timedelta(days=2), PUBLISH_END)))
        t += pd.Timedelta(days=2)

    def one(span):
        rows = _get_json("/datasets/WINDFOR/stream",
                         {"publishDateTimeFrom": _iso(span[0]), "publishDateTimeTo": _iso(span[1])})
        return pd.DataFrame(rows)

    with ThreadPoolExecutor(max_workers=4) as pool:
        frames = list(pool.map(one, spans))
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df = df[(df["startTime"] >= TARGET_START) & (df["startTime"] < TARGET_END)]
    df = df[["publishTime", "startTime", "generation"]]
    return df.drop_duplicates(["publishTime", "startTime"], keep="last").reset_index(drop=True)


class Store:
    """In-memory store, warmed in a background thread so web requests never block on Elexon."""

    def __init__(self):
        self.lock = threading.Lock()
        self.status = "loading"  # loading | ready | error
        self.error = None
        self.actuals = None
        self.forecasts = None
        self.frames = {}  # cutoff -> analysed frame

    def ensure_loaded(self):
        """Serverless (Vercel): lazily read the committed snapshot on first request."""
        if self.status == "ready" or not os.getenv("VERCEL"):
            return
        self.load()

    def load(self, force: bool = False):
        with self.lock:
            self.status, self.error, self.frames = "loading", None, {}
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            fa, ff = os.path.join(DATA_DIR, "actuals.csv.gz"), os.path.join(DATA_DIR, "forecasts.csv.gz")
            if not force and os.path.exists(fa) and os.path.exists(ff):
                actuals = pd.read_csv(fa, parse_dates=["startTime"])
                forecasts = pd.read_csv(ff, parse_dates=["publishTime", "startTime"])
            else:
                actuals, forecasts = fetch_actuals(), fetch_forecasts()
                actuals.to_csv(fa, index=False)
                forecasts.to_csv(ff, index=False)
            with self.lock:
                self.actuals, self.forecasts, self.status = actuals, forecasts, "ready"
            log.info("Loaded %d actuals, %d forecast rows", len(actuals), len(forecasts))
        except Exception as exc:  # noqa: BLE001
            log.exception("Load failed")
            with self.lock:
                self.status, self.error = "error", str(exc)
