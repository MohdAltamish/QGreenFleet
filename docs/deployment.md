# Deployment

## Local
`pip install -r requirements.txt`, then `make dev` (FastAPI on :8000 + React dev server on :5173).
The older Streamlit app still runs with `make demo`.

## Docker (`Dockerfile`)
Two-stage build:
1. `node:20-bookworm-slim` runs `npm ci && npm run build` in `frontend/`.
2. `python:3.11-slim-bookworm` installs WeasyPrint system libraries and `requirements.txt`, copies the repo and the built `frontend/dist`, and runs
   `uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-7860}`.

One process serves `/api/*` (FastAPI) and the React app (all other paths). There is no docker compose file and no database.

## Render (`render.yaml`)
One Docker web service (`qgreenfleet`), `PORT=7860`, health check `/api/health`, auto-deploy on.

## GitLab CI (`.gitlab-ci.yml`)
Stages: lint → test → benchmark-smoke → build (`docker build`, main branch only; no registry push).

## Config/secrets
No secrets are needed. `PORT` sets the server port.
