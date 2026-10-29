# GB Wind Forecast – Day-ahead Decision Support

**Live app (Vercel):** <https://wind-dashboard-eight.vercel.app/> &nbsp;

A full-stack web app (React + Python) that helps an energy utility's day-ahead power-buying team decide how much electricity to procure beyond forecast wind generation. Using Elexon BMRS data for national GB wind (January 2026 delivery days), it answers:

1. **What is the latest wind forecast available at decision time?** For a chosen delivery day and cut-off time, each half-hour uses the most recent forecast published before the cut-off on the previous day. Later forecasts are never used (no look-ahead bias).
2. **How accurate are the forecasts?** Decision-time forecasts are compared with actuals: MAE, RMSE, bias, error percentiles, and breakdowns by day, time of day and error distribution. The error quantiles also give an 80% plausible range and a "downside buffer" (GWh) for the selected day.

**Data (Elexon only):** `FUELHH` (actual wind, `fuelType=WIND`) and `WINDFOR` (wind forecasts with `publishTime`).

**Stack:** React (Vite, Recharts) · Python (FastAPI, pandas) · Docker · Vercel.

---

## Files and directories

```
wind-dashboard/
├── frontend/                 React single-page app
│   ├── src/
│   │   ├── App.jsx           Decision view and Forecast accuracy views
│   │   ├── main.jsx          React entry point
│   │   └── styles.css        Styling (light/dark)
│   ├── index.html
│   ├── package.json          Front-end dependencies and scripts
│   └── vite.config.js        Dev server; proxies /api to the backend (port 8000)
│
├── backend/                  Python API
│   ├── app/
│   │   ├── main.py           FastAPI routes: /api/status, /api/forecast, /api/accuracy, /api/reload
│   │   ├── analysis.py       Picks the decision-time forecast; computes error metrics and ranges
│   │   └── elexon.py         Elexon API client and data cache
│   ├── tests/
│   │   └── test_analysis.py  Unit tests for the core logic
│   ├── data/                 Cached Elexon snapshot (generated; commit it for Vercel)
│   ├── fetch_data.py         One-off script that downloads the snapshot into data/
│   └── requirements.txt      Backend dependencies (local and Docker)
│
├── api/
│   └── index.py              Vercel serverless entry point (exposes the FastAPI app)
│
├── Dockerfile                Multi-stage build: builds the React app, then serves it with the API
├── docker-compose.yml        One-command local run on port 8000
├── .dockerignore / .gitignore
├── vercel.json               Vercel build and routing configuration
├── requirements.txt          Python dependencies installed by Vercel
└── README.md
```

### API

| Endpoint | Description |
|---|---|
| `GET /api/status` | Data loading state (loading / ready / error) |
| `GET /api/forecast?day=2026-01-15&cutoff=09:00` | Decision-time forecast, plausible range, actuals and summary for one day |
| `GET /api/accuracy?cutoff=09:00` | Overall, daily and time-of-day error metrics, error histogram |
| `POST /api/reload` | Re-download data from Elexon (local/Docker only) |

---

## How to start the application

### Step 0 – Prerequisites
- Git
- **Either** Docker (Docker Desktop 4+ / Engine 24+) **or** Python 3.12 and Node.js 20
- Internet access to `data.elexon.co.uk` (no API key needed)
- For deployment: a free [Vercel](https://vercel.com) account and a GitHub account

### Step 1 – Get the code
```bash
git clone <your-repo-url> wind-dashboard
cd wind-dashboard
```

### Step 2 – Run it (choose one)

**Option A – Docker (recommended)**
```bash
docker compose up --build
```
Open <http://localhost:8000>. On first start the app downloads data from Elexon in the background (about a minute); the page shows a loading message until it is ready.

Without compose:
```bash
docker build -t wind-dashboard .
docker run --rm -p 8000:8000 wind-dashboard
```

**Option B – Without Docker (development)**

Terminal 1, backend:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Terminal 2, front end:
```bash
cd frontend
npm install
npm run dev
```
Open <http://localhost:5173>.

### Step 3 – Run the tests
```bash
cd backend
python -m pytest -q
```
Or in Docker, after `docker compose build`:
```bash
docker compose run --rm app python -m pytest -q
```

### Step 4 – Deploy to Vercel
Vercel serves the React build as static files and the FastAPI app as a serverless function. Serverless functions cannot run a long download, so the January 2026 data is saved into the repo once:

1. Download the data snapshot (backend venv from Option B active):
   ```bash
   cd backend
   python fetch_data.py        # creates backend/data/actuals.csv.gz and forecasts.csv.gz
   cd ..
   ```
2. Commit it: `git add -A && git commit -m "Add Elexon Jan-2026 snapshot"`
3. Push the repository to GitHub.
4. Go to <https://vercel.com/new>, import the repo, leave Framework Preset as **Other** (`vercel.json` supplies the build settings) and click **Deploy**.
   CLI alternative: `npm i -g vercel && vercel login && vercel --prod`.
5. Copy the deployment URL into the "Live app" link at the top of this README.

Optional: set `DEFAULT_CUTOFF` (e.g. `09:20`) under Project → Settings → Environment Variables. To refresh the data, re-run step 1, commit and push. Test the function locally with `vercel dev`.

### Troubleshooting
- **"Data load failed":** Elexon is unreachable or the snapshot is missing. Locally, check the logs and call `POST /api/reload`. On Vercel, make sure `backend/data/*.csv.gz` is committed.
- **Behind a corporate proxy:** set `HTTPS_PROXY` when running `fetch_data.py` or Docker.

---

## Assumptions and limitations
- The day-ahead cut-off defaults to **09:00 UK time on the day before delivery**. Change it in the UI (or via `DEFAULT_CUTOFF`) to match the real gate closure of the market you trade on.
- Error = forecast − actual; a positive value means wind was over-forecast (risk of under-buying).
- The plausible range uses empirical error quantiles from the same month (in-sample). It is a practical guide, not a probabilistic forecast.
- Scope is national wind only: no demand, other generation types or other data sources.

## AI Tools used
- Claude