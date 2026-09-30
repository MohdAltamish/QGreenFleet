# Run QGreenFleet locally

## One command

```bash
make dev
```

Starts the FastAPI backend on **:8000** and the React dashboard on **:5173** in one
terminal (their logs are interleaved). `Ctrl+C` stops both. The Makefile uses
`.venv/bin/python` automatically when the virtualenv exists.

| What | URL |
|---|---|
| **Dashboard** | <http://localhost:5173> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| API health check | <http://localhost:8000/api/health> |

### Ports already taken?

Run the two servers on other ports and point the dashboard at the backend:

```bash
.venv/bin/python -m uvicorn src.api.main:app --reload --port 8100
cd frontend && VITE_API_TARGET=http://127.0.0.1:8100 npm run dev -- --port 5180
```

Check what is holding a port with `lsof -ti tcp:8000`.

---

## Production-style, single process

```bash
make frontend-build   # builds frontend/dist
make api              # FastAPI serves /api/* and the built dashboard on :8000
```

The `Dockerfile` does the same in one image (`docker build -t qgreenfleet .`,
then `docker run -p 7860:7860 qgreenfleet`).

---

## First-time setup (only if `.venv` is missing)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend && npm install
```

The backend needs `models/` and a fleet in `data/synthetic/`. Both are committed,
so it starts clean from a fresh clone.

> ⚠️ Do **not** run `make data` before a demo — it regenerates
> `data/synthetic/fleet_20v_5r_seed42.json` differently from the committed
> version, which invalidates every pre-computed case-study result the dashboard
> displays.

---

## Regenerating results

```bash
make train       # EU MRV fuel model -> models/, outputs/mrv_model_report.md
make optimize    # case study (5 scenarios + carbon sweep) -> outputs/case_study/, docs/case-study-results.md
make benchmark   # QIEA vs GA / MOPSO / SA -> outputs/benchmark_results.csv, outputs/benchmark_report.md
make test        # pytest suite
```

## Static demo (no backend)

```bash
cd frontend && node build-static.mjs   # -> frontend/dist-static/qgreenfleet-dashboard.html
```
