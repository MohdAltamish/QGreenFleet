# Deployment

## Local
`pip install -r requirements.txt` → `streamlit run ui/app.py` + `uvicorn src.api.main:app --port 8000`

## Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt . && RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
`docker compose up` runs api + ui + (optional) postgres.

## GitLab CI/CD
- MR pipeline: lint, tests, smoke benchmark
- main pipeline: + docker build & push to registry
- Demo hosting: Streamlit Community Cloud (UI) or a small VM/Render for api+ui

## Config/secrets
Env vars: DATA_DIR, MODEL_PATH, DATABASE_URL (optional). No secrets in repo; use GitLab CI variables.
