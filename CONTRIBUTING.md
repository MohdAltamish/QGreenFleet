# Contributing

1. Fork/branch from `main`: `feature/...`, `fix/...`, `docs/...`
2. Conventional commits: `feat(optimization): add rotation gate decay`
3. All MRs need: passing CI, one approval, updated docs/tests
4. Code style: ruff + type hints; run `ruff check . && pytest -q` before pushing
5. Algorithm changes must update `docs/algorithms.md` and the golden-file test
6. Open issues with the templates: bug / feature / experiment
