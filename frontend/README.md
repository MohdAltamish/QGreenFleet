# QGreenFleet — React frontend

A React dashboard for the QGreenFleet platform (SIH problem #26138). It talks to
the FastAPI backend in [`src/api/`](../src/api), which exposes the project's
prediction surrogate, optimizer, pre-computed policy scenarios, benchmark
results and report artifacts over HTTP.

## Published demo

A static snapshot of this dashboard is published as an Artifact:
<https://claude.ai/code/artifact/434156dc-2345-40c3-97a5-d5d42ab70513>

Build it yourself with `node build-static.mjs` — it captures every API response
into `src/api/snapshot.json` (see `scratchpad/snapshot.py` for the capture
script), builds with `VITE_STATIC_SNAPSHOT=1`, and inlines the bundle into one
self-contained HTML file.

In that build the charts, tables, scenario switching, theme toggle and the fuel
predictor (precomputed across the full slider grid) all work. What needs Python
is disabled with a visible note rather than faked: starting a new optimisation
run (a recorded run of the real engine is shown instead), changing the fleet,
and PDF downloads.

## Run it

The frontend needs the API running. From the repository root:

```bash
# terminal 1 — the backend on :8000
pip install -r requirements.txt
make api                     # uvicorn src.api.main:app --reload --port 8000

# terminal 2 — the dashboard on :5173
make frontend                # npm install && npm run dev
```

Then open <http://localhost:5173>. Vite proxies `/api` to the backend, so the
browser sees a single origin and there is no CORS preflight in development.

Point the proxy elsewhere with `VITE_API_TARGET`:

```bash
VITE_API_TARGET=http://127.0.0.1:8077 npm run dev
```

For a production build served from a different origin than the API, set
`VITE_API_BASE` to the API origin (see [`.env.example`](.env.example)):

```bash
npm run build                # -> dist/
npm run preview              # serve dist/ on :4173
```

The backend needs `models/best.pkl` and a fleet under `data/synthetic/` to be
useful. If they are missing, run `make data && make train` first — the dashboard
reports a degraded status rather than failing silently.

## What each view does

| Route | View | Backed by |
|---|---|---|
| `/` | Headline KPIs, fuel mix, platform status | `GET /api/overview` |
| `/fleet` | Vessel & route catalogue; load, upload or synthesise a fleet | `GET /api/fleet`, `POST /api/fleet/{load,generate,upload-file}` |
| `/predict` | Single-point inference, speed–fuel curves, model registry | `POST /api/predict`, `POST /api/predict/curve`, `GET /api/models` |
| `/optimize` | Live QIEA+QPSO run with progress, Pareto front, deployment plan | `POST /api/optimize`, `GET /api/optimize/{job_id}` |
| `/scenarios` | Pre-computed policy scenarios and the carbon-price sweep | `GET /api/scenarios`, `GET /api/scenarios/{name}`, `GET /api/carbon-sweep` |
| `/benchmark` | QIEA vs GA / MOPSO / SA across four instance sizes | `GET /api/benchmark` |
| `/reports` | PDF exports, the figure library, emission factors | `GET /api/reports`, `GET /api/charts`, `GET /api/emissions/factors` |

Interactive API docs are at <http://localhost:8000/docs> while the backend runs.

## Layout

```
src/
  api/client.js            fetch wrapper; every endpoint in one place
  hooks/                   useResource (fetch + refetch), useOptimizationJob (poll), useTheme
  lib/                     formatters, chart color roles, scale & path maths
  components/              Panel, StatTile, DataTable, Field, States, PlanTable
  components/charts/       hand-rolled SVG charts + the Figure/table-twin wrapper
  pages/                   one file per route
  styles/global.css        design tokens and every component style
```

### Charts

The figures are hand-rolled inline SVG rather than a charting library, so they
meet the project's visualization rules exactly:

- **No dual-axis plots.** Metrics on different scales (hypervolume vs seconds,
  the three objectives) get their own chart rather than a shared second y-axis.
- **Fixed categorical colors.** A fuel, algorithm or ship type keeps its hue
  regardless of how many series are on screen, so filtering never repaints the
  survivors. The 5-slot order is validated colorblind-safe in both light and
  dark mode (worst adjacent CVD ΔE 9.1 light / 8.4 dark).
- **Every chart has a table twin.** The Chart/Table toggle on each figure is the
  WCAG-clean equivalent — no value is reachable only by hovering. It is also the
  relief for the three light-mode series colors that sit below 3:1 contrast
  against the surface.
- **Crosshair tooltips on lines, per-mark tooltips on bars,** nearest-point
  selection on the Pareto scatter, and keyboard focus showing the same readout
  as hover.
- Marks follow one spec: 2px lines, bars capped at 24px with a 4px rounded data
  end, ≥8px markers with a 2px surface ring, solid hairline gridlines.

### Theming

Light is the base palette; the dark steps are a selected set from the same
ramps, declared under both `prefers-color-scheme` and a `[data-theme]` scope so
the in-app toggle wins in either direction. The toggle cycles auto → light →
dark and persists in `localStorage`.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server on :5173 with the `/api` proxy |
| `npm run build` | Production build into `dist/` |
| `npm run preview` | Serve the built output on :4173 |
| `npm run lint` | oxlint over `src/` |
