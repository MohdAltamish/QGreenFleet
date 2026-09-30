"""Capture the API responses the static demo needs into frontend/src/api/snapshot.json.

Runs the FastAPI app in-process (no server), so the snapshot is real engine
output. The prediction grid covers the predictor page's full slider range, and
the recorded optimisation run is a genuine QIEA+QPSO job at a small budget.

Usage::

    python scripts/build_snapshot.py
    cd frontend && node build-static.mjs
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from src.api.main import app  # noqa: E402

OUT = ROOT / "frontend" / "src" / "api" / "snapshot.json"
SHIP_TYPES = ["container", "bulk", "tanker"]
SPEEDS = [8.0 + 0.5 * i for i in range(33)]      # 8–24 kn, the predictor slider
DRAFTS = [4.0 + 0.5 * i for i in range(29)]      # 4–18 m
WEATHER = [0, 1, 2]
RECORDED_RUN = {"pop_size": 50, "generations": 50, "seed": 42, "carbon_price": 0.0, "archive_max": 100}


def get(client: TestClient, path: str) -> dict:
    r = client.get(f"/api{path}")
    r.raise_for_status()
    return r.json()


def main() -> None:
    client = TestClient(app)
    snap: dict = {"generated_from": "src.api.main (in-process)"}

    for key, path in [
        ("health", "/health"), ("overview", "/overview"), ("fleet", "/fleet"), ("fleetFiles", "/fleet/files"),
        ("fleetBau", "/fleet/bau"), ("models", "/models"), ("emissionsFactors", "/emissions/factors"),
        ("scenarios", "/scenarios"), ("carbonSweep", "/carbon-sweep"), ("benchmark", "/benchmark"),
        ("reports", "/reports"), ("charts", "/charts"),
    ]:
        snap[key] = get(client, path)

    snap["scenarioDetails"] = {s["name"]: get(client, f"/scenarios/{s['name']}") for s in snap["scenarios"]["scenarios"]}
    snap["chartData"] = {}
    for name in snap["charts"]["charts"]:
        r = client.get(f"/api/charts/{name}")
        if r.status_code == 200:
            snap["chartData"][name] = "data:image/png;base64," + base64.b64encode(r.content).decode()

    # Prediction grid: [t/day, draft-weather factor] per speed, keyed "type|weather|draft".
    values: dict[str, list[list[float]]] = {}
    for st in SHIP_TYPES:
        for w in WEATHER:
            for d in DRAFTS:
                curve = client.post("/api/predict/curve", json={
                    "ship_types": [st], "speed_min": SPEEDS[0], "speed_max": SPEEDS[-1],
                    "points": len(SPEEDS), "draft_m": d, "weather_severity": w,
                }).json()
                adj = client.post("/api/predict", json={
                    "ship_type": st, "speed_kn": 14.0, "draft_m": d, "weather_severity": w,
                }).json()["hydrodynamic_adjustment"]
                values[f"{st}|{w}|{d:.1f}"] = [
                    [round(p["fuel_tons_per_day"], 4), round(adj, 5)] for p in curve["series"][0]["points"]
                ]
    snap["predictionGrid"] = {
        "ship_types": SHIP_TYPES, "speeds": SPEEDS, "drafts": DRAFTS, "weather": WEATHER,
        "model_name": snap["health"]["predictor"]["model_name"],
        "two_stage": snap["health"]["predictor"]["two_stage"], "values": values,
    }

    # A genuine optimisation job, polled to completion.
    job = client.post("/api/optimize", json=RECORDED_RUN).json()
    while True:
        state = get(client, f"/optimize/{job['job_id']}?include_result=true")
        if state["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(0.5)
    if state["status"] != "done":
        raise SystemExit(f"Recorded run ended with status {state['status']}: {state.get('error')}")
    state["job_id"], state["started_at"] = "recorded", "recorded"
    snap["recordedRun"] = state

    OUT.write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
