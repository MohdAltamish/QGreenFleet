"""FastAPI application exposing QGreenFleet to the React frontend.

Serves the prediction surrogate, fleet management, pre-computed policy
scenarios, live QIEA+QPSO optimization jobs, benchmark results and report
artifacts. Run with::

    uvicorn src.api.main:app --reload --port 8000
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import numpy as np

from src.api import paths
from src.api.schemas import (
    FleetGenerateRequest,
    FleetLoadRequest,
    FleetUploadRequest,
    OptimizeRequest,
    PredictCurveRequest,
    PredictRequest,
)
from src.api.serialize import to_jsonable
from src.api.service import SERVICE
from src.emissions.factors import (
    FUEL_FACTORS,
    OPTIMIZER_FUELS,
    summary_table,
    wtw_gco2e_per_mj,
)

API_PREFIX = "/api"

app = FastAPI(
    title="QGreenFleet API",
    version="0.3.0",
    description=(
        "Quantum-inspired fuel prediction and green fleet optimization "
        "(SIH problem #26138). Backs the QGreenFleet React dashboard."
    ),
)

# The dev frontend runs on a different origin (Vite on :5173), so CORS is
# required. Tightened to localhost origins rather than a blanket wildcard.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
#  Health & metadata                                                           #
# --------------------------------------------------------------------------- #
@app.get(f"{API_PREFIX}/health", tags=["system"])
def health() -> dict[str, Any]:
    """Report which artifacts and models are present on this deployment."""
    predictor = SERVICE.predictor_status()
    scenarios = list(SERVICE.scenarios())
    try:
        fleet = SERVICE.get_fleet()
        fleet_status = {
            "loaded": True,
            "source": fleet["source"],
            "vessels": len(fleet["vessels"]),
            "routes": len(fleet["routes"]),
        }
    except Exception as exc:  # noqa: BLE001
        fleet_status = {"loaded": False, "error": str(exc)}

    return {
        "status": "ok" if predictor["available"] else "degraded",
        "version": app.version,
        "predictor": predictor,
        "fleet": fleet_status,
        "scenarios": scenarios,
        "artifacts": {
            "benchmark_results": paths.BENCHMARK_CSV.exists(),
            "carbon_sweep": paths.CARBON_SWEEP_CSV.exists(),
            "executive_summary_pdf": (paths.SAMPLE_REPORTS / "QGreenFleet_Executive_Summary.pdf").exists(),
            "technical_report_pdf": (paths.SAMPLE_REPORTS / "QGreenFleet_Technical_Report.pdf").exists(),
            "charts": sorted(p.name for p in paths.CHARTS.glob("*.png")) if paths.CHARTS.exists() else [],
        },
    }


@app.get(f"{API_PREFIX}/overview", tags=["system"])
def overview() -> dict[str, Any]:
    """Landing-page KPIs: fleet size, headline deltas and optimizer advantage."""
    try:
        fleet = SERVICE.get_fleet()
        fleet_size, routes_count = len(fleet["vessels"]), len(fleet["routes"])
    except Exception:  # noqa: BLE001
        fleet_size, routes_count = 0, 0

    predictor = SERVICE.predictor_status()
    baseline: dict[str, Any] | None = None
    if "baseline" in SERVICE.scenarios():
        detail = SERVICE.scenario_detail("baseline")
        baseline = {
            "deltas": detail["deltas"],
            "fuel_mix_pct": detail["fuel_mix_pct"],
            "pareto_size": len(detail["pareto"]),
            "elapsed_seconds": detail["elapsed_seconds"],
        }

    bench = SERVICE.benchmark()
    speedup: float | None = None
    if bench["available"]:
        rows = bench["by_instance"]
        qiea = [r["wall_time_s"] for r in rows if r["algo"] == "QIEA" and r.get("wall_time_s")]
        ga = [r["wall_time_s"] for r in rows if r["algo"] == "GA" and r.get("wall_time_s")]
        if qiea and ga:
            speedup = round(float(np.mean(ga)) / float(np.mean(qiea)), 2)

    return to_jsonable({
        "fleet_size": fleet_size,
        "routes_count": routes_count,
        "predictor": predictor,
        "scenarios": [
            {"name": n, "label": paths.SCENARIO_LABELS.get(n, n)} for n in SERVICE.scenarios()
        ],
        "baseline": baseline,
        "optimizer_speedup_vs_ga": speedup,
        "fuels": list(OPTIMIZER_FUELS),
    })


# --------------------------------------------------------------------------- #
#  Fleet                                                                       #
# --------------------------------------------------------------------------- #
@app.get(f"{API_PREFIX}/fleet", tags=["fleet"])
def get_fleet() -> dict[str, Any]:
    """The active fleet catalog with vessel and route detail."""
    try:
        fleet = SERVICE.get_fleet()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_jsonable({
        "source": fleet["source"],
        "seed": fleet.get("seed"),
        "vessels": fleet["vessels"],
        "routes": fleet["routes"],
        "totals": {
            "vessels": len(fleet["vessels"]),
            "routes": len(fleet["routes"]),
            "dwt": sum(float(v.get("dwt", 0)) for v in fleet["vessels"]),
            "capacity_teu": sum(float(v.get("capacity_teu", 0)) for v in fleet["vessels"]),
            "demand_teu": sum(float(r.get("demand_teu", 0)) for r in fleet["routes"]),
            "distance_nm": sum(float(r.get("distance_nm", 0)) for r in fleet["routes"]),
        },
    })


@app.get(f"{API_PREFIX}/fleet/files", tags=["fleet"])
def list_fleet_files() -> dict[str, Any]:
    """Fleet JSON files available under data/synthetic."""
    return {"files": SERVICE.available_fleet_files()}


@app.post(f"{API_PREFIX}/fleet/load", tags=["fleet"])
def load_fleet(req: FleetLoadRequest) -> dict[str, Any]:
    """Activate one of the fleet files under data/synthetic."""
    try:
        SERVICE.load_fleet_file(req.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return get_fleet()


@app.post(f"{API_PREFIX}/fleet/generate", tags=["fleet"])
def generate_fleet(req: FleetGenerateRequest) -> dict[str, Any]:
    """Synthesize an MRV-calibrated fleet and make it the active fleet."""
    try:
        SERVICE.generate_fleet(req.vessels, req.routes, req.seed)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Fleet generation failed: {exc}") from exc
    return get_fleet()


@app.post(f"{API_PREFIX}/fleet/upload", tags=["fleet"])
def upload_fleet_json(req: FleetUploadRequest) -> dict[str, Any]:
    """Activate an inline fleet specification."""
    try:
        SERVICE.set_fleet(req.model_dump(exclude={"source"}), req.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return get_fleet()


@app.post(f"{API_PREFIX}/fleet/upload-file", tags=["fleet"])
async def upload_fleet_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """Activate a fleet from an uploaded JSON file."""
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Not valid JSON: {exc}") from exc
    try:
        SERVICE.set_fleet(data, file.filename or "uploaded.json")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return get_fleet()


@app.get(f"{API_PREFIX}/fleet/bau", tags=["fleet"])
def fleet_bau() -> dict[str, Any]:
    """Business-As-Usual baseline for the active fleet (all HFO, design speed)."""
    from src.api.serialize import solution_payload

    try:
        fleet = SERVICE.get_fleet()
        bau = SERVICE.get_bau()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return solution_payload(bau, fleet["vessels"], fleet["routes"], "bau")


# --------------------------------------------------------------------------- #
#  Prediction                                                                  #
# --------------------------------------------------------------------------- #
@app.post(f"{API_PREFIX}/predict", tags=["prediction"])
def predict(req: PredictRequest) -> dict[str, Any]:
    """Predict fuel consumption in tons/day for one operating point."""
    try:
        predictor = SERVICE.predictor
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Predictor unavailable: {exc}") from exc

    tpd = float(predictor.predict_tpd(
        speed_kn=req.speed_kn,
        draft_m=req.draft_m,
        weather_severity=req.weather_severity,
        ship_type=req.ship_type,
        route_type=req.route_type,
        maintenance_status=req.maintenance_status,
    ))
    adjustment = float(predictor.compute_adjustment_ratio(
        draft_m=req.draft_m,
        weather_severity=req.weather_severity,
        ship_type=req.ship_type,
        speed_kn=req.speed_kn,
    ))

    return {
        "request": req.model_dump(),
        "fuel_tons_per_day": tpd,
        "fuel_kg_per_hour": tpd * 1000.0 / 24.0,
        "fuel_kg_per_nm": (tpd * 1000.0 / 24.0) / max(1e-6, req.speed_kn),
        "hydrodynamic_adjustment": adjustment,
        "model_name": predictor.model_name,
        "two_stage": bool(predictor.has_mrv),
    }


@app.post(f"{API_PREFIX}/predict/curve", tags=["prediction"])
def predict_curve(req: PredictCurveRequest) -> dict[str, Any]:
    """Speed-fuel admiralty curves across ship types for the given conditions."""
    if req.speed_max <= req.speed_min:
        raise HTTPException(status_code=422, detail="speed_max must exceed speed_min.")
    try:
        predictor = SERVICE.predictor
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Predictor unavailable: {exc}") from exc

    speeds = np.linspace(req.speed_min, req.speed_max, req.points)
    series: list[dict[str, Any]] = []
    for ship_type in req.ship_types:
        tpd = np.atleast_1d(predictor.predict_tpd(
            speed_kn=speeds,
            draft_m=req.draft_m,
            weather_severity=req.weather_severity,
            ship_type=ship_type,
        ))
        series.append({
            "ship_type": ship_type,
            "points": [
                {"speed_kn": round(float(s), 2), "fuel_tons_per_day": float(f)}
                for s, f in zip(speeds, tpd)
            ],
        })

    return to_jsonable({
        "draft_m": req.draft_m,
        "weather_severity": req.weather_severity,
        "model_name": predictor.model_name,
        "series": series,
    })


@app.get(f"{API_PREFIX}/models", tags=["prediction"])
def models() -> dict[str, Any]:
    """Surrogate model registry and the active predictor's metadata."""
    return to_jsonable({
        "registry": SERVICE.model_registry(),
        "active": SERVICE.predictor_status(),
    })


# --------------------------------------------------------------------------- #
#  Emissions                                                                   #
# --------------------------------------------------------------------------- #
@app.get(f"{API_PREFIX}/emissions/factors", tags=["emissions"])
def emissions_factors() -> dict[str, Any]:
    """TtW / WtT / WtW greenhouse gas intensities for every supported fuel."""
    rows = []
    for row in summary_table():
        name = str(row["fuel"])
        rows.append({
            **row,
            "optimizer_selectable": name in OPTIMIZER_FUELS,
            "raw": FUEL_FACTORS[name],
        })
    return to_jsonable({
        "fuels": rows,
        "optimizer_fuels": list(OPTIMIZER_FUELS),
        "wtw_by_fuel": {f: round(wtw_gco2e_per_mj(f), 2) for f in FUEL_FACTORS},
    })


# --------------------------------------------------------------------------- #
#  Scenarios                                                                   #
# --------------------------------------------------------------------------- #
@app.get(f"{API_PREFIX}/scenarios", tags=["scenarios"])
def list_scenarios() -> dict[str, Any]:
    """Pre-computed policy scenarios with their headline KPIs."""
    items: list[dict[str, Any]] = []
    for name, scen in SERVICE.scenarios().items():
        summary = scen.get("summary") or {}
        items.append({
            "name": name,
            "label": paths.SCENARIO_LABELS.get(name, name),
            "pareto_size": len(scen["pareto"]),
            "elapsed_seconds": summary.get("elapsed_seconds"),
            "knee_kpis": summary.get("knee_kpis"),
            "bau_kpis": summary.get("bau_kpis"),
            "deltas": summary.get("deltas"),
            "fuel_mix_pct": summary.get("fuel_mix_pct"),
            "fuel_switches_count": summary.get("fuel_switches_count"),
            "avg_speed_delta_kn": summary.get("avg_speed_delta_kn"),
        })
    return to_jsonable({"scenarios": items})


@app.get(f"{API_PREFIX}/scenarios/{{name}}", tags=["scenarios"])
def scenario_detail(name: str) -> dict[str, Any]:
    """Full detail for one scenario: Pareto front, knee, BAU deltas, deployment plan."""
    try:
        return SERVICE.scenario_detail(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario '{name}' has not been pre-computed. Available: {list(SERVICE.scenarios())}",
        ) from exc


@app.get(f"{API_PREFIX}/scenarios/{{name}}/report", tags=["scenarios"])
def scenario_report(name: str) -> dict[str, Any]:
    """Unified report payload for a scenario (KPI deltas, options, model metrics)."""
    try:
        return SERVICE.scenario_report(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Scenario '{name}' not found.") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Report build failed: {exc}") from exc


@app.get(f"{API_PREFIX}/carbon-sweep", tags=["scenarios"])
def carbon_sweep() -> dict[str, Any]:
    """Pre-computed carbon price sensitivity sweep."""
    return SERVICE.carbon_sweep()


# --------------------------------------------------------------------------- #
#  Optimization                                                                #
# --------------------------------------------------------------------------- #
@app.post(f"{API_PREFIX}/optimize", status_code=202, tags=["optimization"])
def start_optimization(req: OptimizeRequest) -> dict[str, Any]:
    """Start a live QIEA + QPSO run in the background and return its job handle."""
    try:
        config = req.to_config()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        job = SERVICE.start_optimization(config)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Could not start optimization: {exc}") from exc
    return job.progress_payload()


@app.get(f"{API_PREFIX}/optimize/jobs", tags=["optimization"])
def list_jobs() -> dict[str, Any]:
    """Every optimization job known to this API process, newest first."""
    return {
        "jobs": [
            {k: v for k, v in job.progress_payload().items() if k != "result"}
            for job in SERVICE.jobs()
        ]
    }


@app.get(f"{API_PREFIX}/optimize/{{job_id}}", tags=["optimization"])
def job_status(
    job_id: str,
    include_result: bool = Query(True, description="Include the full result once the job is done."),
) -> dict[str, Any]:
    """Poll an optimization job's progress and, once finished, its results."""
    try:
        job = SERVICE.job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.") from exc
    payload = job.progress_payload()
    if not include_result:
        payload.pop("result", None)
    return payload


@app.delete(f"{API_PREFIX}/optimize/{{job_id}}", tags=["optimization"])
def cancel_job(job_id: str) -> dict[str, Any]:
    """Request cancellation of a running job at its next generation boundary."""
    try:
        job = SERVICE.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.") from exc
    return job.progress_payload()


# --------------------------------------------------------------------------- #
#  Benchmark                                                                   #
# --------------------------------------------------------------------------- #
@app.get(f"{API_PREFIX}/benchmark", tags=["benchmark"])
def benchmark() -> dict[str, Any]:
    """Multi-algorithm benchmark results (QIEA vs GA / MOPSO / SA)."""
    return SERVICE.benchmark()


# --------------------------------------------------------------------------- #
#  Report & chart artifacts                                                    #
# --------------------------------------------------------------------------- #
REPORT_FILES = {
    "executive-summary": ("QGreenFleet_Executive_Summary.pdf", "Executive Summary"),
    "technical-report": ("QGreenFleet_Technical_Report.pdf", "Technical Report"),
}


@app.get(f"{API_PREFIX}/reports", tags=["reports"])
def list_reports() -> dict[str, Any]:
    """Report PDFs available for download."""
    items = []
    for key, (filename, label) in REPORT_FILES.items():
        path = paths.SAMPLE_REPORTS / filename
        items.append({
            "key": key,
            "label": label,
            "filename": filename,
            "available": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else None,
        })
    return {"reports": items}


@app.get(f"{API_PREFIX}/reports/{{key}}", tags=["reports"])
def download_report(key: str) -> FileResponse:
    """Download one of the pre-compiled report PDFs."""
    entry = REPORT_FILES.get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown report '{key}'.")
    path = paths.SAMPLE_REPORTS / entry[0]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{entry[1]} has not been generated yet.")
    return FileResponse(path, media_type="application/pdf", filename=entry[0])


@app.get(f"{API_PREFIX}/charts", tags=["reports"])
def list_charts() -> dict[str, Any]:
    """Figure library rendered by the analysis pipeline."""
    charts = sorted(p.name for p in paths.CHARTS.glob("*.png")) if paths.CHARTS.exists() else []
    outputs = sorted(p.name for p in paths.OUTPUTS.glob("*.png")) if paths.OUTPUTS.exists() else []
    return {"charts": charts, "outputs": outputs}


@app.get(f"{API_PREFIX}/charts/{{name}}", tags=["reports"])
def get_chart(name: str) -> FileResponse:
    """Serve one PNG figure from charts/ or outputs/."""
    if not name.endswith(".png") or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Only bare .png file names are served.")
    for directory in (paths.CHARTS, paths.OUTPUTS):
        candidate = (directory / name).resolve()
        if candidate.parent == directory.resolve() and candidate.exists():
            return FileResponse(candidate, media_type="image/png")
    raise HTTPException(status_code=404, detail=f"Figure '{name}' not found.")
