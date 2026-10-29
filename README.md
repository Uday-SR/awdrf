# Day-ahead wind forecast – decision support (GB, January 2026)

A small full-stack app for a UK utility's day-ahead power-buying team. For national GB wind generation it shows:

1. **Decision view** – for a chosen delivery day, the *latest forecast that was actually available at the day-ahead decision time*, an 80% plausible range, and (hindsight) the actual outcome.
2. **Forecast accuracy** – quantified error (MAE, RMSE, bias, error percentiles, daily / time-of-day / distribution views) of those decision-time forecasts vs. actuals.

**Stack:** React (Vite + Recharts) · Python (FastAPI + pandas) · Docker · Vercel.
**Data (Elexon BMRS only):** `FUELHH` (fuelType `WIND`, actuals) and `WINDFOR` (forecasts), January 2026 delivery days.

## How it works

* A forecast for delivery day **D** is only usable if published **before the day-ahead gate on D‑1**. The cut-off is a UI setting (default **09:00 UK time**, a conservative assumption – check the exact gate closure of the venue you trade on and change it).
* For every half-hour of D the backend picks the **latest `publishTime` ≤ cut-off** (`backend/app/analysis.py`). This avoids look-ahead bias: forecasts published after the decision are never used.
* Error = forecast − actual (positive = wind over-forecast → risk of under-buying). The "80% range" shifts the forecast by the P10/P90 of historical error, giving a "downside buffer" in GWh.
* Locally/Docker: on startup the backend downloads data in the background (~1 min) and caches it in `backend/data` (`DATA_DIR`). The UI shows a loading state until ready.
* On Vercel: a pre-downloaded snapshot committed to the repo (`backend/data/*.csv.gz`) is read instead, because serverless functions cannot run long downloads.

### API
| Endpoint | Purpose |
|---|---|
| `GET /api/status` | loading / ready / error |
| `GET /api/forecast?day=2026-01-15&cutoff=09:00` | decision-time forecast, range, actuals, summary |
| `GET /api/accuracy?cutoff=09:00` | overall, daily, by-time-of-day metrics, error histogram |
| `POST /api/reload` | force re-download from Elexon |

## Installation guide

### Step 0 – Prerequisites
* Git, and **either** Docker (Docker Desktop 4+/Engine 24+) **or** Python 3.12 + Node.js 20.
* Internet access to `data.elexon.co.uk` (no API key required).
* For deployment: a free [Vercel](https://vercel.com) account and a GitHub account.

### Step 1 – Get the code
```bash
git clone <your-repo-url> wind-dashboard
cd wind-dashboard
```

### Option A – Run with Docker (recommended)
```bash
docker compose up --build
```
Open http://localhost:8000. Wait ~1 minute for "Fetching data from Elexon…" to finish.
Or without compose:
```bash
docker build -t wind-dashboard .
docker run --rm -p 8000:8000 wind-dashboard
```

### Option B – Run locally without Docker (development)
Backend (terminal 1):
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Frontend (terminal 2):
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 (Vite proxies `/api` to port 8000).

### Step 2 – Run the tests
```bash
cd backend && python -m pytest -q
```
In Docker (after `docker compose build`):
```bash
docker compose run --rm app python -m pytest -q
```

### Step 3 – Deploy to Vercel
Vercel serves the React build as static files and the FastAPI app as a serverless function (`api/index.py`).
Because functions can't run a long download, the January 2026 data is saved into the repo once.

1. Download the data snapshot (needs internet; run with the backend venv from Option B active):
   ```bash
   cd backend
   python fetch_data.py        # creates backend/data/actuals.csv.gz and forecasts.csv.gz
   cd ..
   ```
2. Commit it: `git add -A && git commit -m "Add Elexon Jan-2026 snapshot"`
3. Push the repo to GitHub.
4. At https://vercel.com/new import the repo. Leave Framework Preset as **Other**; `vercel.json` supplies build settings. Click **Deploy**.
   Or via CLI: `npm i -g vercel && vercel login && vercel --prod`.
5. Open the URL Vercel prints.

Optional: set `DEFAULT_CUTOFF` (e.g. `09:20`) under Project → Settings → Environment Variables.
To refresh the data: re-run step 1, commit, push. Test the function locally with `vercel dev`.

### Troubleshooting
* *"Data load failed"* – Elexon unreachable or the snapshot is missing. Locally, check the logs and `POST /api/reload`. On Vercel, make sure `backend/data/*.csv.gz` is committed.
* *Behind a corporate proxy* – set `HTTPS_PROXY` when running `fetch_data.py` or Docker.

## Limitations / possible extensions
* Wind only, national level; the error band is an in-sample empirical quantile of January errors, not a probabilistic forecast.
* Error by forecast horizon (using every vintage, not just the decision-time one), error conditional on wind level, and a demand/residual-load view are natural next steps.
