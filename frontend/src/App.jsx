import { useEffect, useState } from "react";
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

const DAYS = Array.from({ length: 31 }, (_, i) => `2026-01-${String(i + 1).padStart(2, "0")}`);
const mw = (v) => (v == null ? "–" : `${Math.round(v).toLocaleString("en-GB")} MW`);
const gwh = (v) => (v == null ? "–" : `${(v / 1000).toFixed(1)} GWh`);
const pct = (v) => (v == null ? "–" : `${v.toFixed(1)}%`);
const fmtTime = (iso) =>
  new Date(iso).toLocaleString("en-GB", { timeZone: "Europe/London", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

async function api(path) {
  const r = await fetch(path);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body;
}

function useApi(path, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let cancel = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    api(path).then((data) => !cancel && setState({ data, error: null, loading: false }))
      .catch((error) => !cancel && setState({ data: null, error: error.message, loading: false }));
    return () => { cancel = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

const Kpi = ({ label, value, sub }) => (
  <div className="card kpi" style={{ marginBottom: 0 }}>
    <div className="l">{label}</div><div className="v">{value}</div>{sub && <div className="s">{sub}</div>}
  </div>
);

function DayView({ day, cutoff }) {
  const { data, error, loading } = useApi(`/api/forecast?day=${day}&cutoff=${cutoff}`, [day, cutoff]);
  if (loading) return <div className="msg">Loading…</div>;
  if (error) return <div className="msg warn">{error}</div>;
  const s = data.summary;
  const rows = data.series.map((r) => ({ ...r, band: [r.lower, r.upper] }));
  return (
    <>
      <div className="grid">
        <Kpi label="Forecast wind energy" value={gwh(s.forecast_mwh)} sub={`Peak ${mw(s.peak_forecast_mw)} · Min ${mw(s.min_forecast_mw)}`} />
        <Kpi label="Plausible range (80%)" value={`${gwh(s.p10_mwh)} – ${gwh(s.p90_mwh)}`} sub="Forecast adjusted by Jan-2026 error quantiles" />
        <Kpi label="Downside buffer" value={gwh(s.downside_buffer_mwh)} sub="Extra non-wind energy to consider covering (P10 case)" />
        <Kpi label="Latest forecast used" value={fmtTime(s.latest_publish_time)} sub={`Gate cut-off ${fmtTime(s.cutoff_time)} (UK) · ${s.n_vintages} vintage(s)`} />
      </div>
      <div className="card">
        <h3>Wind generation on {day}: forecast available at decision time vs. actual</h3>
        <div className="sub">Each half-hour uses the most recent forecast published before the cut-off on the previous day.</div>
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="slot" interval={3} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} unit=" MW" width={80} />
            <Tooltip formatter={(v) => (Array.isArray(v) ? `${Math.round(v[0])} – ${Math.round(v[1])} MW` : `${Math.round(v)} MW`)} />
            <Legend />
            <Area dataKey="band" name="80% range" fill="#0b6bcb" fillOpacity={0.15} stroke="none" />
            <Line dataKey="forecast" name="Forecast" stroke="#0b6bcb" dot={false} strokeWidth={2} />
            <Line dataKey="actual" name="Actual" stroke="#d9480f" dot={false} strokeWidth={2} />
          </ComposedChart>
        </ResponsiveContainer>
        {s.actual_mwh != null && s.day_metrics && (
          <p className="note">
            Outcome for this day: actual {gwh(s.actual_mwh)} vs forecast {gwh(s.forecast_mwh)} · MAE {mw(s.day_metrics.mae)} · bias {mw(s.day_metrics.bias)}
          </p>
        )}
      </div>
    </>
  );
}

function Accuracy({ cutoff }) {
  const { data, error, loading } = useApi(`/api/accuracy?cutoff=${cutoff}`, [cutoff]);
  if (loading) return <div className="msg">Loading…</div>;
  if (error) return <div className="msg warn">{error}</div>;
  const o = data.overall;
  return (
    <>
      <div className="grid">
        <Kpi label="MAE" value={mw(o.mae)} sub={`${pct(o.nmae_pct)} of mean actual (${mw(o.mean_actual)})`} />
        <Kpi label="RMSE" value={mw(o.rmse)} sub="Penalises large misses" />
        <Kpi label="Bias (forecast − actual)" value={mw(o.bias)} sub={o.bias > 0 ? "Over-forecasts wind on average" : "Under-forecasts wind on average"} />
        <Kpi label="90% of errors within" value={`± ${mw(o.p90_abs_error)}`} sub={`Error P10 ${mw(o.err_p10)} · P90 ${mw(o.err_p90)}`} />
      </div>
      <div className="card">
        <h3>Daily MAE</h3><div className="sub">Mean absolute error per delivery day (MW)</div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data.daily.map((d) => ({ ...d, day: d.date.slice(8) }))}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" /><XAxis dataKey="day" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={60} /><Tooltip formatter={(v) => mw(v)} />
            <ReferenceLine y={o.mae} stroke="#d9480f" strokeDasharray="4 4" />
            <Bar dataKey="mae" name="MAE" fill="#0b6bcb" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="card">
        <h3>Error by time of day</h3><div className="sub">MAE and bias per half-hour of the delivery day (UK time)</div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data.by_slot}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" /><XAxis dataKey="slot" interval={3} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={60} /><Tooltip formatter={(v) => mw(v)} /><Legend />
            <Line dataKey="mae" name="MAE" stroke="#0b6bcb" dot={false} />
            <Line dataKey="bias" name="Bias" stroke="#d9480f" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="card">
        <h3>Error distribution</h3><div className="sub">Count of half-hours by forecast error (forecast − actual), 500 MW bins. Left of zero = wind under-forecast; right = over-forecast.</div>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data.histogram}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" /><XAxis dataKey="bin_start" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={50} /><Tooltip /><Bar dataKey="count" fill="#0b6bcb" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

export default function App() {
  const [tab, setTab] = useState("day");
  const [day, setDay] = useState("2026-01-15");
  const [cutoff, setCutoff] = useState("09:00");
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let timer;
    const poll = () => api("/api/status").then((s) => {
      setStatus(s);
      if (s.status === "loading") timer = setTimeout(poll, 3000);
    }).catch(() => (timer = setTimeout(poll, 5000)));
    poll();
    return () => clearTimeout(timer);
  }, []);

  const ready = status?.status === "ready";
  return (
    <>
      <header>
        <h1>Day-ahead wind forecast – decision support</h1>
        <p>GB national wind (Elexon WINDFOR forecasts vs FUELHH actuals) · purchase decisions for January 2026 delivery days</p>
      </header>
      <main>
        <div className="controls">
          <div className="tabs">
            <button className={tab === "day" ? "on" : ""} onClick={() => setTab("day")}>Decision view</button>
            <button className={tab === "acc" ? "on" : ""} onClick={() => setTab("acc")}>Forecast accuracy</button>
          </div>
          {tab === "day" && (
            <label>Delivery day
              <select value={day} onChange={(e) => setDay(e.target.value)}>{DAYS.map((d) => <option key={d}>{d}</option>)}</select>
            </label>
          )}
          <label>Decision cut-off (UK time, day before)
            <input type="time" value={cutoff} onChange={(e) => e.target.value && setCutoff(e.target.value)} />
          </label>
        </div>
        {!status && <div className="msg">Connecting…</div>}
        {status?.status === "loading" && <div className="msg">Fetching data from Elexon (first start takes ~1 minute)…</div>}
        {status?.status === "error" && <div className="msg warn">Data load failed: {status.error}</div>}
        {ready && (tab === "day" ? <DayView day={day} cutoff={cutoff} /> : <Accuracy cutoff={cutoff} />)}
        <p className="note">
          Error = forecast − actual. Accuracy and the 80% range use only the forecast that was available at the chosen cut-off, across all January 2026 delivery days (in-sample).
          Wind only – demand and other generation are out of scope.
        </p>
      </main>
    </>
  );
}
