.PHONY: help test data train optimize benchmark demo api frontend frontend-install frontend-build all

PYTHON := python3

help:
	@echo "QGreenFleet (SIH #26138) Command Center"
	@echo ""
	@echo "Targets:"
	@echo "  make test       Run full pytest verification suite (77+ tests)"
	@echo "  make data       Process EU MRV/Kaggle datasets & generate synthetic fleets"
	@echo "  make train      Train & calibrate predictive models (Physics, QPSO-XGBoost)"
	@echo "  make optimize   Execute baseline green fleet optimization"
	@echo "  make benchmark  Execute multi-algorithm benchmarking suite (S, M, L, XL)"
	@echo "  make demo       Launch interactive Streamlit decision support platform"
	@echo "  make api        Serve the FastAPI backend on :8000 (React frontend)"
	@echo "  make frontend   Launch the React dashboard dev server on :5173"
	@echo "  make all        Run full pipeline end-to-end"

test:
	$(PYTHON) -m pytest -q

data:
	$(PYTHON) -m src.data.prepare
	$(PYTHON) -m src.data.generate_synthetic --vessels 20 --routes 5 --seed 42

train:
	$(PYTHON) -m src.prediction.train

optimize:
	$(PYTHON) -m src.case_study.run --fast

benchmark:
	$(PYTHON) -m src.benchmark.run_all --config configs/benchmark.yaml

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

all: test data train optimize benchmark
