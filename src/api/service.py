"""Stateful service layer backing the QGreenFleet HTTP API.

Owns the three pieces of process-wide state the API needs:
    * the lazily loaded `FuelPredictor` surrogate (expensive to construct),
    * the currently active fleet plus its BAU baseline,
    * the registry of live QIEA+QPSO optimization jobs.

All heavy artifacts (case-study scenarios, benchmark CSV) are read from disk on
first use and memoized, mirroring the caching the Streamlit UI performs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable
import uuid

import numpy as np
import pandas as pd

from src.api import paths
from src.api.serialize import objectives_of, to_jsonable
from src.data.generate_synthetic import generate as generate_fleet
from src.emissions.factors import OPTIMIZER_FUELS
from src.optimization.bau import DEFAULT_FUEL_PRICES, compute_bau_baseline
from src.optimization.individual import Solution
from src.prediction.predictor import FuelPredictor

# `ui.utils.report_data` is framework-free (numpy/pandas only) and is the
# project's single source of truth for KPI deltas — the test suite imports it
# the same way, so the API reuses it rather than duplicating the logic.
from ui.utils.report_data import _find_knee_solution, build_report_data


# Human-readable fuel names, for the change descriptions the UI shows verbatim.
FUEL_DISPLAY: dict[str, str] = {
    "HFO": "HFO",
    "LNG_DIESEL": "LNG (Diesel cycle)",
    "MEOH_GREEN": "green methanol",
    "H2_GREEN": "green hydrogen",
    "NH3_GREEN": "green ammonia",
}


# --------------------------------------------------------------------------- #
#  Fleet validation                                                            #
# --------------------------------------------------------------------------- #
def validate_fleet(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate a fleet payload and backfill optional vessel/route fields.

    Raises:
        ValueError: If vessels or routes are missing or empty.
    """
    vessels = data.get("vessels") or []
    routes = data.get("routes") or []
    if not isinstance(vessels, list) or not vessels:
        raise ValueError("Fleet payload is missing a non-empty 'vessels' array.")
    if not isinstance(routes, list) or not routes:
        raise ValueError("Fleet payload is missing a non-empty 'routes' array.")

    for idx, v in enumerate(vessels):
        v.setdefault("id", f"V{idx:03d}")
        v.setdefault("type", "container")
        v.setdefault("design_speed", 15.0)
        v.setdefault("fuels_allowed", ["HFO"])
        if "capacity_teu" not in v:
            dwt = float(v.get("dwt", 50_000))
            v["capacity_teu"] = int(dwt / 12) if v["type"] == "container" else int(dwt)

    for idx, r in enumerate(routes):
        r.setdefault("id", f"R{idx}")
        r.setdefault("distance_nm", 1000.0)
        r.setdefault("demand_teu", 2000)
        r.setdefault("schedule_days", 7.0)

    return vessels, routes


# --------------------------------------------------------------------------- #
#  Optimization jobs                                                           #
# --------------------------------------------------------------------------- #
@dataclass
class OptimizationJob:
    """A single background QIEA+QPSO run and its live progress."""

    job_id: str
    config: dict[str, Any]
    fleet_size: int
    routes_count: int
    status: str = "queued"  # queued | running | done | error | cancelled
    generation: int = 0
    total_generations: int = 0
    archive_size: int = 0
    hypervolume: float = 0.0
    feasible_count: int = 0
    started_at: str = ""
    elapsed_seconds: float = 0.0
    error: str | None = None
    result: dict[str, Any] | None = None
    cancel_requested: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def progress_payload(self) -> dict[str, Any]:
        """Snapshot of job state safe to return over HTTP."""
        with self._lock:
            pct = (
                round(100.0 * self.generation / self.total_generations, 1)
                if self.total_generations
                else 0.0
            )
            payload = {
                "job_id": self.job_id,
                "status": self.status,
                "generation": self.generation,
                "total_generations": self.total_generations,
                "progress_pct": pct,
                "archive_size": self.archive_size,
                "hypervolume": self.hypervolume,
                "feasible_count": self.feasible_count,
                "population_size": self.config.get("pop_size"),
                "fleet_size": self.fleet_size,
                "routes_count": self.routes_count,
                "started_at": self.started_at,
                "elapsed_seconds": round(self.elapsed_seconds, 2),
                "error": self.error,
                "result": self.result,
            }
        return to_jsonable(payload)


class JobCancelled(RuntimeError):
    """Raised inside the optimizer callback to abort a cancelled job."""


class QGreenFleetService:
    """Process-wide state and artifact access for the API."""

    MAX_JOBS = 20

    def __init__(self) -> None:
        self._predictor: FuelPredictor | None = None
        self._predictor_error: str | None = None
        self._predictor_lock = threading.Lock()

        self._fleet: dict[str, Any] | None = None
        self._bau: Solution | None = None
        self._fleet_lock = threading.Lock()

        self._scenarios: dict[str, dict[str, Any]] | None = None
        self._scenario_lock = threading.Lock()

        self._jobs: dict[str, OptimizationJob] = {}
        self._jobs_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  Predictor                                                          #
    # ------------------------------------------------------------------ #
    @property
    def predictor(self) -> FuelPredictor:
        """Lazily construct the ML surrogate, raising if the models are absent."""
        with self._predictor_lock:
            if self._predictor is None:
                try:
                    self._predictor = FuelPredictor()
                    self._predictor_error = None
                except Exception as exc:  # noqa: BLE001 — surfaced verbatim to the client
                    self._predictor_error = str(exc)
                    raise
            return self._predictor

    def predictor_status(self) -> dict[str, Any]:
        """Report surrogate availability without raising."""
        try:
            p = self.predictor
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc), "model_name": None, "two_stage": False}
        return {
            "available": True,
            "error": None,
            "model_name": p.model_name,
            "two_stage": bool(p.has_mrv),
            "metrics": to_jsonable(p.metrics),
            "feature_columns": list(p.feature_columns),
        }

    # ------------------------------------------------------------------ #
    #  Active fleet                                                       #
    # ------------------------------------------------------------------ #
    def get_fleet(self) -> dict[str, Any]:
        """Return the active fleet, loading the default synthetic fleet on first use."""
        with self._fleet_lock:
            if self._fleet is None:
                if not paths.DEFAULT_FLEET.exists():
                    raise FileNotFoundError(
                        f"Default fleet not found at {paths.DEFAULT_FLEET}. "
                        "Run 'make data' or POST /api/fleet/generate."
                    )
                data = json.loads(paths.DEFAULT_FLEET.read_text(encoding="utf-8"))
                vessels, routes = validate_fleet(data)
                self._fleet = {
                    "vessels": vessels,
                    "routes": routes,
                    "source": paths.DEFAULT_FLEET.name,
                    "seed": data.get("seed"),
                }
            return self._fleet

    def set_fleet(self, data: dict[str, Any], source: str) -> dict[str, Any]:
        """Replace the active fleet and invalidate the cached BAU baseline."""
        vessels, routes = validate_fleet(data)
        with self._fleet_lock:
            self._fleet = {
                "vessels": vessels,
                "routes": routes,
                "source": source,
                "seed": data.get("seed"),
            }
            self._bau = None
            return self._fleet

    def load_fleet_file(self, name: str) -> dict[str, Any]:
        """Load one of the fleet JSON files shipped in data/synthetic."""
        target = (paths.DATA_SYNTHETIC / name).resolve()
        if target.parent != paths.DATA_SYNTHETIC.resolve() or not target.exists():
            raise FileNotFoundError(f"Fleet file '{name}' not found in data/synthetic.")
        return self.set_fleet(json.loads(target.read_text(encoding="utf-8")), target.name)

    def generate_fleet(self, n_vessels: int, n_routes: int, seed: int) -> dict[str, Any]:
        """Synthesize a new MRV-calibrated fleet and make it active."""
        out_path = generate_fleet(n_vessels=n_vessels, n_routes=n_routes, seed=seed)
        return self.set_fleet(json.loads(out_path.read_text(encoding="utf-8")), out_path.name)

    def available_fleet_files(self) -> list[dict[str, Any]]:
        """List the fleet JSON files on disk with their vessel/route counts."""
        if not paths.DATA_SYNTHETIC.exists():
            return []
        files: list[dict[str, Any]] = []
        for p in sorted(paths.DATA_SYNTHETIC.glob("fleet_*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                files.append({
                    "name": p.name,
                    "vessels": len(data.get("vessels", [])),
                    "routes": len(data.get("routes", [])),
                    "seed": data.get("seed"),
                })
            except Exception:  # noqa: BLE001 — skip unreadable files
                continue
        return files

    def get_bau(
        self,
        fuel_prices: dict[str, float] | None = None,
        carbon_price: float = 0.0,
    ) -> Solution:
        """Compute (and cache, for default prices) the BAU baseline for the active fleet."""
        fleet = self.get_fleet()
        is_default = fuel_prices is None and carbon_price == 0.0
        if is_default:
            with self._fleet_lock:
                if self._bau is not None:
                    return self._bau

        bau = compute_bau_baseline(
            vessels=fleet["vessels"],
            routes=fleet["routes"],
            predictor=self.predictor,
            fuel_prices=fuel_prices,
            carbon_price=carbon_price,
        )
        if is_default:
            with self._fleet_lock:
                self._bau = bau
        return bau

    # ------------------------------------------------------------------ #
    #  Pre-computed case-study scenarios                                  #
    # ------------------------------------------------------------------ #
    def scenarios(self) -> dict[str, dict[str, Any]]:
        """Load every pre-computed case-study scenario found on disk (memoized)."""
        with self._scenario_lock:
            if self._scenarios is not None:
                return self._scenarios

            loaded: dict[str, dict[str, Any]] = {}
            if paths.CASE_STUDY.exists():
                dirs = [paths.CASE_STUDY / n for n in paths.KNOWN_SCENARIOS]
                dirs += [d for d in sorted(paths.CASE_STUDY.iterdir()) if d.is_dir() and d not in dirs]
                for d in dirs:
                    if not (d / "pareto.csv").exists():
                        continue
                    try:
                        loaded[d.name] = self._read_scenario_dir(d)
                    except Exception:  # noqa: BLE001 — a broken scenario must not break the list
                        continue
            self._scenarios = loaded
            return loaded

    @staticmethod
    def _read_scenario_dir(d: Path) -> dict[str, Any]:
        """Read one scenario directory's pareto/knee/BAU/history/summary artifacts."""
        def _json(name: str) -> Any:
            p = d / name
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

        pareto_df = pd.read_csv(d / "pareto.csv")
        return {
            "name": d.name,
            "pareto": pareto_df.to_dict(orient="records"),
            "knee": _json("solution_knee.json"),
            "bau": _json("bau_baseline.json"),
            "history": _json("history.json"),
            "summary": _json("summary.json"),
        }

    def scenario(self, name: str) -> dict[str, Any]:
        """Return one scenario's artifacts.

        Raises:
            KeyError: If the scenario has not been pre-computed.
        """
        scen = self.scenarios().get(name)
        if scen is None:
            raise KeyError(name)
        return scen

    def scenario_report(self, name: str) -> dict[str, Any]:
        """Build the unified report payload (KPI deltas, plan, options) for a scenario."""
        scen = self.scenario(name)
        pareto = scen["pareto"]
        knee = scen["knee"] or _find_knee_solution(pareto)[0]
        bau = scen["bau"] or knee
        fleet = self.get_fleet()
        return to_jsonable(
            build_report_data(
                solution=knee,
                pareto=pareto,
                history=scen.get("history"),
                fleet=fleet,
                bau=bau,
                scenarios=None,
                sweep_results=None,
            )
        )

    # ------------------------------------------------------------------ #
    #  Scenario detail                                                    #
    # ------------------------------------------------------------------ #
    def scenario_detail(self, name: str) -> dict[str, Any]:
        """Return everything the dashboard needs for one pre-computed scenario.

        The persisted knee/BAU artifacts already carry an explicit per-vessel
        plan, so the deployment table and fuel mix are derived by joining those
        lists on vessel_id rather than from the numpy decision matrices.
        """
        scen = self.scenario(name)
        pareto = scen["pareto"]
        knee = scen["knee"]
        bau = scen["bau"]
        summary = scen.get("summary") or {}

        knee_index = next(
            (i for i, row in enumerate(pareto) if row.get("is_knee")),
            None,
        )
        if knee_index is None:
            knee_index = _find_knee_solution(pareto)[1]
        if knee is None:
            knee = pareto[knee_index]

        plan = self._join_plan(knee, bau)
        fuel_mix = self._fuel_mix_pct(plan)

        k1, k2, k3 = objectives_of(knee)
        deltas: dict[str, Any] | None = None
        if bau is not None:
            b1, b2, b3 = objectives_of(bau)
            deltas = {
                "fuel_cost": self._delta(b1, k1),
                "ghg_wtw": self._delta(b2, k2),
                "opex": self._delta(b3, k3),
            }

        return to_jsonable({
            "name": name,
            "label": paths.SCENARIO_LABELS.get(name, name),
            "summary": summary,
            "pareto": [
                {**row, "is_knee": bool(row.get("is_knee", i == knee_index))}
                for i, row in enumerate(pareto)
            ],
            "knee_index": knee_index,
            "knee": {
                "solution_id": knee.get("solution_id") or knee.get("id") or f"sol_{knee_index:03d}",
                "objectives": dict(zip(("fuel_cost_usd", "ghg_wtw_tco2e", "opex_usd"), (k1, k2, k3))),
                "feasible": bool(knee.get("feasible", True)),
                "violations": knee.get("violations", {}),
            },
            "bau": None if bau is None else {
                "objectives": dict(zip(("fuel_cost_usd", "ghg_wtw_tco2e", "opex_usd"), objectives_of(bau))),
                "feasible": bool(bau.get("feasible", True)),
                "violations": bau.get("violations", {}),
            },
            "deltas": deltas,
            "three_options": self._three_options(pareto, knee_index),
            "plan": plan,
            "fuel_mix_pct": fuel_mix,
            "history": scen.get("history"),
            "elapsed_seconds": summary.get("elapsed_seconds"),
        })

    @staticmethod
    def _delta(bau_val: float, opt_val: float) -> dict[str, Any]:
        """Absolute and percentage change of an optimized KPI against BAU."""
        change = opt_val - bau_val
        return {
            "bau": bau_val,
            "opt": opt_val,
            "delta": change,
            "delta_pct": (change / bau_val * 100.0) if bau_val else 0.0,
        }

    def _join_plan(
        self,
        knee: dict[str, Any],
        bau: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Join the optimized and BAU per-vessel plans, annotating what changed."""
        fleet = self.get_fleet()
        catalog = {v.get("id"): v for v in fleet["vessels"]}
        opt_rows = knee.get("vessels") if isinstance(knee.get("vessels"), list) else []
        bau_rows = bau.get("vessels") if bau and isinstance(bau.get("vessels"), list) else []
        bau_by_id = {r.get("vessel_id"): r for r in bau_rows}

        plan: list[dict[str, Any]] = []
        for row in opt_rows:
            vid = row.get("vessel_id")
            vessel = catalog.get(vid, {})
            bau_row = bau_by_id.get(vid, {})

            speed = float(row.get("speed_kn") or 0.0)
            bau_speed = float(bau_row.get("speed_kn") or speed)
            fuel = row.get("fuel") or "HFO"
            bau_fuel = bau_row.get("fuel") or "HFO"
            route = row.get("route_id") or "Reserve"
            speed_delta = speed - bau_speed

            changes: list[str] = []
            if fuel != bau_fuel:
                changes.append(f"switched to {FUEL_DISPLAY.get(fuel, fuel)}")
            if abs(speed_delta) >= 0.4:
                changes.append(f"{'slowed' if speed_delta < 0 else 'increased'} {abs(speed_delta):.1f} kn")
            if row.get("shore_power") and not bau_row.get("shore_power"):
                changes.append("shore power on")

            plan.append({
                "vessel_id": vid,
                "type": row.get("type") or vessel.get("type"),
                "dwt": vessel.get("dwt"),
                "capacity_teu": vessel.get("capacity_teu"),
                "route_id": route,
                "assigned": route not in ("Unassigned", "Reserve"),
                "speed_kn": round(speed, 1),
                "bau_speed_kn": round(bau_speed, 1),
                "speed_delta_kn": round(speed_delta, 1),
                "fuel": fuel,
                "bau_fuel": bau_fuel,
                "shore_power": bool(row.get("shore_power", False)),
                "fuels_allowed": vessel.get("fuels_allowed", []),
                "change_vs_bau": ", ".join(changes) if changes else "no change",
            })
        return plan

    @staticmethod
    def _fuel_mix_pct(plan: list[dict[str, Any]]) -> dict[str, float]:
        """Share of deployed vessels per fuel, in percent."""
        deployed = [row for row in plan if row.get("assigned")] or plan
        if not deployed:
            return {}
        counts: dict[str, int] = {}
        for row in deployed:
            counts[row["fuel"]] = counts.get(row["fuel"], 0) + 1
        return {k: round(v / len(deployed) * 100.0, 1) for k, v in sorted(counts.items())}

    def _three_options(
        self,
        pareto: list[dict[str, Any]],
        knee_index: int,
    ) -> list[dict[str, Any]]:
        """Cheapest / recommended / greenest picks from a Pareto front."""
        if not pareto:
            return []
        cheapest = min(pareto, key=lambda r: objectives_of(r)[0])
        greenest = min(pareto, key=lambda r: objectives_of(r)[1])
        recommended = pareto[knee_index]
        base_cost = objectives_of(cheapest)[0]

        tiers = (
            ("Cheapest", cheapest, "Tight budgets"),
            ("Recommended", recommended, "Balanced trade-off"),
            ("Greenest", greenest, "Emission targets"),
        )
        options: list[dict[str, Any]] = []
        for tier, row, best_for in tiers:
            z1, z2, z3 = objectives_of(row)
            options.append({
                "tier": tier,
                "solution_id": row.get("solution_id") or row.get("id"),
                "fuel_cost_usd": z1,
                "ghg_wtw_tco2e": z2,
                "opex_usd": z3,
                "extra_cost_vs_cheapest": z1 - base_cost,
                "best_for": best_for,
            })
        return options

    # ------------------------------------------------------------------ #
    #  Optimization jobs                                                  #
    # ------------------------------------------------------------------ #
    def start_optimization(self, config: dict[str, Any]) -> OptimizationJob:
        """Launch a QIEA+QPSO run on a daemon thread and return its job handle."""
        fleet = self.get_fleet()
        predictor = self.predictor  # fail fast if the surrogate is unavailable

        job = OptimizationJob(
            job_id=uuid.uuid4().hex[:12],
            config=config,
            fleet_size=len(fleet["vessels"]),
            routes_count=len(fleet["routes"]),
            total_generations=int(config.get("generations", 50)),
            started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        with self._jobs_lock:
            # Bound memory: drop the oldest finished jobs once the registry is full.
            if len(self._jobs) >= self.MAX_JOBS:
                finished = [
                    j for j in self._jobs.values()
                    if j.status in ("done", "error", "cancelled")
                ]
                for stale in sorted(finished, key=lambda j: j.started_at)[: len(finished) // 2 + 1]:
                    self._jobs.pop(stale.job_id, None)
            self._jobs[job.job_id] = job

        thread = threading.Thread(
            target=self._run_optimization,
            args=(job, fleet, predictor),
            name=f"qgf-opt-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return job

    def _run_optimization(
        self,
        job: OptimizationJob,
        fleet: dict[str, Any],
        predictor: FuelPredictor,
    ) -> None:
        """Thread body: run the optimizer, recording progress and the final archive."""
        from src.optimization.qiea import run as run_qiea

        vessels, routes = fleet["vessels"], fleet["routes"]
        t0 = time.time()
        with job._lock:
            job.status = "running"

        def on_progress(gen: int, total: int, n_archive: int, hv: float, n_feasible: int) -> None:
            with job._lock:
                if job.cancel_requested:
                    raise JobCancelled
                job.generation = gen
                job.total_generations = total
                job.archive_size = n_archive
                job.hypervolume = float(hv)
                job.feasible_count = n_feasible
                job.elapsed_seconds = time.time() - t0

        try:
            archive, history = run_qiea(
                vessels=vessels,
                routes=routes,
                config=job.config,
                predictor=predictor,
                progress_callback=on_progress,
            )
        except JobCancelled:
            with job._lock:
                job.status = "cancelled"
                job.elapsed_seconds = time.time() - t0
            return
        except Exception as exc:  # noqa: BLE001 — reported to the client verbatim
            with job._lock:
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                job.elapsed_seconds = time.time() - t0
            return

        elapsed = time.time() - t0
        try:
            result = self.build_run_result(archive, history, vessels, routes, job.config, elapsed)
        except Exception as exc:  # noqa: BLE001
            with job._lock:
                job.status = "error"
                job.error = f"Result assembly failed: {type(exc).__name__}: {exc}"
                job.elapsed_seconds = elapsed
            return

        with job._lock:
            job.status = "done"
            job.result = result
            job.elapsed_seconds = elapsed
            job.archive_size = len(archive)

    def build_run_result(
        self,
        archive: list[Any],
        history: dict[str, list[Any]],
        vessels: list[dict[str, Any]],
        routes: list[dict[str, Any]],
        config: dict[str, Any],
        elapsed: float,
    ) -> dict[str, Any]:
        """Assemble the Pareto front, knee solution, BAU deltas and plan for a run."""
        from src.api.serialize import pareto_payload, solution_payload

        knee_sol, knee_idx = _find_knee_solution(archive)
        bau = self.get_bau(
            fuel_prices=config.get("fuel_prices"),
            carbon_price=float(config.get("carbon_price", 0.0)),
        )
        report = build_report_data(
            solution=knee_sol,
            pareto=archive,
            history=history,
            fleet={"vessels": vessels, "routes": routes},
            bau=bau,
            scenarios=None,
            sweep_results=None,
        )
        return to_jsonable({
            "elapsed_seconds": round(elapsed, 2),
            "config": config,
            "pareto": pareto_payload(archive, vessels, routes, knee_index=knee_idx),
            "knee": solution_payload(knee_sol, vessels, routes, f"sol_{knee_idx:03d}"),
            "knee_index": knee_idx,
            "bau": solution_payload(bau, vessels, routes, "bau"),
            "history": history,
            "report": report,
        })

    def job(self, job_id: str) -> OptimizationJob:
        """Look up a job by id.

        Raises:
            KeyError: If no such job exists in this process.
        """
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def jobs(self) -> list[OptimizationJob]:
        """All jobs known to this process, newest first."""
        with self._jobs_lock:
            return sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)

    def cancel_job(self, job_id: str) -> OptimizationJob:
        """Signal a running job to stop at its next generation boundary."""
        job = self.job(job_id)
        with job._lock:
            if job.status in ("queued", "running"):
                job.cancel_requested = True
        return job

    # ------------------------------------------------------------------ #
    #  Static artifacts                                                   #
    # ------------------------------------------------------------------ #
    def benchmark(self) -> dict[str, Any]:
        """Aggregate the multi-algorithm benchmark CSV per (algorithm, instance)."""
        if not paths.BENCHMARK_CSV.exists():
            return {"available": False, "rows": [], "by_instance": [], "instances": [], "algorithms": []}

        df = pd.read_csv(paths.BENCHMARK_CSV)
        instance_order = {"S": 1, "M": 2, "L": 3, "XL": 4}
        numeric = [c for c in ("hv", "igd", "wall_time_s", "archive_size", "feasible_count") if c in df.columns]
        grouped = (
            df.groupby(["algo", "instance"])[numeric]
            .mean()
            .reset_index()
            .sort_values("instance", key=lambda s: s.map(lambda x: instance_order.get(str(x), 99)))
        )
        instances = sorted(df["instance"].astype(str).unique(), key=lambda x: instance_order.get(x, 99))
        return to_jsonable({
            "available": True,
            "rows": df.replace({np.nan: None}).to_dict(orient="records"),
            "by_instance": grouped.replace({np.nan: None}).to_dict(orient="records"),
            "instances": instances,
            "algorithms": sorted(df["algo"].astype(str).unique()),
            "seeds": sorted(int(s) for s in df["seed"].unique()) if "seed" in df.columns else [],
        })

    def carbon_sweep(self) -> dict[str, Any]:
        """Return the pre-computed carbon-price sensitivity sweep, if present."""
        if not paths.CARBON_SWEEP_CSV.exists():
            return {"available": False, "rows": []}
        df = pd.read_csv(paths.CARBON_SWEEP_CSV)
        return to_jsonable({
            "available": True,
            "rows": df.replace({np.nan: None}).to_dict(orient="records"),
            "columns": list(df.columns),
        })

    @staticmethod
    def model_registry() -> list[dict[str, Any]]:
        """Surrogate model selection table, read from trained metadata when available."""
        registry: list[dict[str, Any]] = []
        mrv_meta_path = paths.MODELS / "mrv_best_meta.json"
        if mrv_meta_path.exists():
            try:
                meta = json.loads(mrv_meta_path.read_text(encoding="utf-8"))
                cv = meta.get("cv_5fold", {})
                test = meta.get("test_metrics", {})
                default = meta.get("default_xgb_metrics", {})
                registry.append({
                    "model": "MRV QPSO-XGBoost (real EU MRV)",
                    "stage": "Stage 1 — macro empirical",
                    "cv_rmse": f"{cv.get('rmse_mean', 0):.2f} ± {cv.get('rmse_std', 0):.2f} kg/nm",
                    "test_rmse": f"{test.get('rmse', 0):.2f} kg/nm",
                    "test_mape": f"{test.get('mape', 0):.1f}%",
                    "selected": True,
                })
                if default:
                    registry.append({
                        "model": "MRV XGBoost (default hyperparameters)",
                        "stage": "Stage 1 — macro empirical",
                        "cv_rmse": "—",
                        "test_rmse": f"{default.get('rmse', 0):.2f} kg/nm",
                        "test_mape": f"{default.get('mape', 0):.1f}%",
                        "selected": False,
                    })
            except Exception:  # noqa: BLE001
                pass

        voyage_meta_path = paths.MODELS / "best_meta.json"
        if voyage_meta_path.exists():
            try:
                meta = json.loads(voyage_meta_path.read_text(encoding="utf-8"))
                m = meta.get("metrics", {})
                registry.append({
                    "model": f"Voyage {meta.get('model_name', 'surrogate')}",
                    "stage": "Stage 2 — micro hydrodynamic",
                    "cv_rmse": f"{m.get('cv_rmse_mean', 0):.2f} ± {m.get('cv_rmse_std', 0):.2f} t/d"
                    if "cv_rmse_mean" in m else "—",
                    "test_rmse": f"{m.get('rmse', 0):.2f} t/d" if "rmse" in m else "—",
                    "test_mape": f"{m.get('mape', 0):.1f}%" if "mape" in m else "—",
                    "selected": True,
                })
            except Exception:  # noqa: BLE001
                pass
        return registry


SERVICE = QGreenFleetService()
