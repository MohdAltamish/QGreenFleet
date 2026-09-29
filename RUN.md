# Run QGreenFleet locally

Two terminals. Backend first, then frontend.

## Terminal 1 — backend (FastAPI)

```bash
cd "/Users/vibhorsharma/ps138/ QGreenFleet"
source .venv/bin/activate
python -m uvicorn src.api.main:app --reload --port 8100
```

## Terminal 2 — frontend (React)

```bash
cd "/Users/vibhorsharma/ps138/ QGreenFleet/frontend"
VITE_API_TARGET=http://127.0.0.1:8100 npm run dev -- --port 5180
```

## Open

| What | URL |
|---|---|
| **Dashboard** | <http://localhost:5180> |
| API docs (Swagger) | <http://localhost:8100/docs> |
| API health check | <http://localhost:8100/api/health> |

Stop either server with `Ctrl+C`.

---

## Why ports 8100 / 5180 and not 8000 / 5173?

The `ps147` project runs a uvicorn backend on **8000** and a Vite server on
**5173**. If that project is not running you can use the default ports and the
Makefile shortcuts instead:

```bash
source .venv/bin/activate
make api        # backend  on :8000
make frontend   # frontend on :5173
```

Check what is holding a port with `lsof -ti tcp:8000`.

---

## First-time setup (only if `.venv` is missing)

```bash
cd "/Users/vibhorsharma/ps138/ QGreenFleet"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install
```

The backend needs `models/best.pkl` and a fleet in `data/synthetic/`. Both are
committed, so it should start clean.

> ⚠️ Do **not** run `make data` before a demo — it regenerates
> `data/synthetic/fleet_20v_5r_seed42.json` differently from the committed
> version, which invalidates every pre-computed case-study result the dashboard
> displays.

---

## Published static demo (no backend needed)

<https://claude.ai/code/artifact/434156dc-2345-40c3-97a5-d5d42ab70513>

Rebuild it with:

```bash
cd frontend && node build-static.mjs
```

---

## Other useful commands

```bash
source .venv/bin/activate
pytest -q                          # 96 tests
python -m streamlit run ui/app.py  # the original Streamlit app, :8501
cd frontend && npm run build        # production frontend build -> dist/
```
