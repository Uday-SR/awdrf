import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import analysis
from .elexon import Store

logging.basicConfig(level=logging.INFO)
store = Store()
DEFAULT_CUTOFF = os.getenv("DEFAULT_CUTOFF", "09:00")


@asynccontextmanager
async def lifespan(_app):
    if not os.getenv("VERCEL"):  # on Vercel the snapshot is read lazily instead
        threading.Thread(target=store.load, daemon=True).start()  # warm cache in background
    yield


app = FastAPI(title="Wind forecast decision support", lifespan=lifespan)


def get_frame(cutoff: str):
    store.ensure_loaded()
    if store.status != "ready":
        raise HTTPException(503, f"Data {store.status}: {store.error or 'please retry shortly'}")
    try:
        if cutoff not in store.frames:
            store.frames[cutoff] = analysis.build_frame(store.forecasts, store.actuals, cutoff)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return store.frames[cutoff]


@app.get("/api/status")
def status():
    store.ensure_loaded()
    return {"status": store.status, "error": store.error, "default_cutoff": DEFAULT_CUTOFF,
            "month": "2026-01"}


@app.post("/api/reload")
def reload():
    if os.getenv("VERCEL"):
        raise HTTPException(501, "Read-only snapshot on Vercel; re-run fetch_data.py and redeploy")
    threading.Thread(target=store.load, kwargs={"force": True}, daemon=True).start()
    return {"status": "loading"}


@app.get("/api/forecast")
def forecast(day: str = Query(..., pattern=r"^2026-01-\d{2}$"), cutoff: str = DEFAULT_CUTOFF):
    res = analysis.day_view(get_frame(cutoff), day, cutoff)
    if res is None:
        raise HTTPException(404, f"No forecast available for {day}")
    return analysis.clean(res)


@app.get("/api/accuracy")
def accuracy(cutoff: str = DEFAULT_CUTOFF):
    return analysis.clean(analysis.accuracy(get_frame(cutoff)))


# Serve the built React app (present in the Docker image)
STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "static"))
if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
