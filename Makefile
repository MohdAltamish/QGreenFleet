.PHONY: help test data train optimize optimize-fast benchmark demo api frontend frontend-install frontend-build dev all

# Use the project virtualenv when it exists, so `make api` works without activating it.
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

help:
	@echo "QGreenFleet (SIH #26138)"
	@echo ""
	@echo "Targets:"
	@echo "  make dev            Run the API (:8000) and the React dashboard (:5173) together"
	@echo "  make test           Run the pytest suite"
	@echo "  make data           Process EU MRV / Kaggle data and generate synthetic fleets"
	@echo "  make train          Train the EU MRV fuel model and the voyage-level candidates"
	@echo "  make optimize       Case study: 5 scenarios + carbon sweep at the full budget (~15 min)"
	@echo "  make optimize-fast  Same at a reduced budget, for a quick check"
	@echo "  make benchmark      QIEA vs GA / MOPSO / SA on instances S, M, L, XL (fresh run)"
	@echo "  make api            FastAPI backend on :8000 (also serves frontend/dist if built)"
	@echo "  make frontend       React dashboard dev server on :5173"
	@echo "  make demo           Legacy Streamlit app"
	@echo "  make all            Full pipeline end to end"

test:
	$(PYTHON) -m pytest -q

data:
	$(PYTHON) -m src.data.prepare
	$(PYTHON) -m src.data.generate_synthetic --vessels 20 --routes 5 --seed 42

train:
	$(PYTHON) -m src.prediction.mrv_model
	$(PYTHON) -m src.prediction.train

optimize:
	$(PYTHON) -m src.case_study.run

optimize-fast:
	$(PYTHON) -m src.case_study.run --fast

benchmark:
	$(PYTHON) -m src.benchmark.run_all --config configs/benchmark.yaml --no-resume

demo:
	$(PYTHON) -m streamlit run ui/app.py

api:
	$(PYTHON) -m uvicorn src.api.main:app --reload --port 8000

frontend-install:
	cd frontend && npm install

frontend: frontend-install
	cd frontend && npm run dev

frontend-build: frontend-install
	cd frontend && npm run build

dev:
	$(MAKE) -j2 api frontend

all: test data train optimize benchmark
