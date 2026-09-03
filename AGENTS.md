# AGENTS.md — AI Agent Instructions for this Repo

## Project context
Quantum-inspired fuel prediction + multi-objective green fleet optimization (SIH #26138). Read `project.md`, `docs/design.md`, `docs/algorithms.md` before coding.

## Conventions
- Python 3.11, type hints everywhere, dataclasses for domain models
- Vectorize with NumPy; no per-vessel Python loops in hot paths
- All randomness through a seeded `numpy.random.Generator` passed in
- Configs in YAML; never hardcode hyperparameters
- Tests in `tests/` mirror `src/`; pytest; every equation in mathematical-model.md needs a unit test
- Docstrings: Google style; cite equation numbers from docs/mathematical-model.md

## Guardrails
- Do not change the Solution encoding (Q-matrix + speed vector) without updating algorithms.md
- Do not add heavyweight deps (no TensorFlow, no Gurobi); MILP uses HiGHS
- Keep predictor and optimizer decoupled (predictor injected as callable)
- Benchmark fairness: all algorithms share the same evaluation budget and repair operators

## Task workflow
1. Read relevant doc section 2. Write/adjust test 3. Implement 4. Run `pytest -q` 5. Update docs if behavior changed
