"""Filesystem locations for QGreenFleet API artifacts."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_SYNTHETIC = PROJECT_ROOT / "data" / "synthetic"
OUTPUTS = PROJECT_ROOT / "outputs"
CASE_STUDY = OUTPUTS / "case_study"
CHARTS = PROJECT_ROOT / "charts"
FLOWCHARTS = PROJECT_ROOT / "flowchart"
MODELS = PROJECT_ROOT / "models"
CONFIGS = PROJECT_ROOT / "configs"
SAMPLE_REPORTS = PROJECT_ROOT / "docs" / "samples"

DEFAULT_FLEET = DATA_SYNTHETIC / "fleet_20v_5r_seed42.json"
BENCHMARK_CSV = OUTPUTS / "benchmark_results.csv"
CARBON_SWEEP_CSV = CASE_STUDY / "carbon_sweep.csv"

KNOWN_SCENARIOS: tuple[str, ...] = (
    "baseline",
    "carbon_100",
    "cii_tightened",
    "meoh_subsidized",
)

SCENARIO_LABELS: dict[str, str] = {
    "baseline": "Baseline ($0 carbon price)",
    "carbon_100": "Carbon price $100/t-CO₂e",
    "cii_tightened": "IMO CII bands tightened",
    "meoh_subsidized": "Green methanol subsidised",
}
