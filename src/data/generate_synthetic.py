"""Generate synthetic fleets calibrated to MRV stats.
Run: python -m src.data.generate_synthetic --vessels 20 --routes 5 --seed 42
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT = _PROJECT_ROOT / "data" / "synthetic"
OUT.mkdir(parents=True, exist_ok=True)

# fallbacks if MRV not available: (dwt_lo, dwt_hi, design_speed, fuel_per_nm_kg)
DEFAULTS = {
    "container": (15_000, 150_000, 20.0, 250),
    "bulk": (25_000, 200_000, 14.0, 180),
    "tanker": (30_000, 300_000, 14.5, 200),
}


def calibrate() -> dict[str, float]:
    """Return per-type fuel_per_nm from real MRV data if available."""
    p = _PROJECT_ROOT / "data" / "processed" / "mrv_clean.parquet"
    if not p.exists():
        return {k: v[3] for k, v in DEFAULTS.items()}
    mrv = pd.read_parquet(p)
    med = mrv.groupby("category")["fuel_per_nm_kg"].median().to_dict()
    return {k: med.get(k, v[3]) for k, v in DEFAULTS.items()}


def generate(n_vessels: int, n_routes: int, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    fuel_cal = calibrate()
    types = rng.choice(list(DEFAULTS), size=n_vessels, p=[0.4, 0.35, 0.25])

    vessels = []
    for i, t in enumerate(types):
        lo, hi, spd, _ = DEFAULTS[t]
        dwt = float(rng.uniform(lo, hi))

        # Fuel availability per vessel — not everyone gets all three
        if t == "container":
            v_fuels = ["HFO"]
            if rng.random() < 0.5:
                v_fuels.append("LNG_DIESEL")
            if rng.random() < 0.25:
                v_fuels.append("MEOH_GREEN")
        else:  # bulk / tanker
            v_fuels = ["HFO"]
            if rng.random() < 0.35:
                v_fuels.append("LNG_DIESEL")

        vessels.append({
            "id": f"V{i:03d}", "type": t, "dwt": round(dwt),
            "capacity_teu": round(dwt / 12) if t == "container" else round(dwt),
            "engine_kw": round(dwt * rng.uniform(0.25, 0.45)),
            "design_speed": round(float(rng.normal(spd, 1.5)), 1),
            "vmin": 8.0, "vmax": round(spd + 4, 1),
            "fuel_per_nm_kg": round(fuel_cal[t] * (dwt / 80_000) ** 0.66, 1),
            "fuels_allowed": v_fuels,
            "charter_per_day": round(8000 + dwt * 0.15),
        })

    routes = []
    for j in range(n_routes):
        dist = float(rng.uniform(500, 8000))
        # Schedule pressure: 30% of routes get tight schedules (5% slack)
        if rng.random() < 0.3:
            sched = dist / (24 * 14) * 1.05          # tight: near max-speed required
        else:
            sched = dist / (24 * 12) * rng.uniform(1.15, 1.4)  # normal slack
        routes.append({
            "id": f"R{j}", "distance_nm": round(dist),
            "schedule_days": round(sched, 1),
            "demand_teu": round(float(rng.lognormal(9.5, 0.4))),
            "weather_severity": int(rng.integers(0, 3)),
            "lng_available": bool(rng.random() < 0.5),
            "meoh_available": bool(rng.random() < 0.25),
            "shore_power": bool(rng.random() < 0.4),
        })

    fleet = {"seed": seed, "vessels": vessels, "routes": routes}
    fname = OUT / f"fleet_{n_vessels}v_{n_routes}r_seed{seed}.json"
    fname.write_text(json.dumps(fleet, indent=2))
    print(f"Wrote {fname} ({n_vessels} vessels, {n_routes} routes)")
    return fname


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--vessels", type=int, default=20)
    ap.add_argument("--routes", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    generate(a.vessels, a.routes, a.seed)
