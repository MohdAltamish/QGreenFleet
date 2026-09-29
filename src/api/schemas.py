"""Request models for the QGreenFleet HTTP API.

Responses are returned as plain JSON-serializable dicts assembled by the
service layer; only inputs are validated with pydantic.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.emissions.factors import OPTIMIZER_FUELS

SHIP_TYPES = ("container", "bulk", "tanker")


class FleetGenerateRequest(BaseModel):
    """Parameters for synthesizing an MRV-calibrated fleet."""

    vessels: int = Field(20, ge=2, le=200, description="Number of vessels to synthesize.")
    routes: int = Field(5, ge=1, le=25, description="Number of commercial route corridors.")
    seed: int = Field(42, ge=0, le=9999, description="Random generator seed.")


class FleetLoadRequest(BaseModel):
    """Select one of the fleet JSON files under data/synthetic."""

    name: str = Field(..., description="File name inside data/synthetic, e.g. fleet_20v_5r_seed42.json")


class FleetUploadRequest(BaseModel):
    """An inline fleet specification."""

    vessels: list[dict[str, Any]] = Field(..., min_length=1)
    routes: list[dict[str, Any]] = Field(..., min_length=1)
    seed: int | None = None
    source: str = Field("uploaded.json", description="Label recorded as the fleet source.")


class PredictRequest(BaseModel):
    """A single-point fuel consumption inference."""

    ship_type: Literal["container", "bulk", "tanker"] = "container"
    speed_kn: float = Field(15.0, ge=1.0, le=40.0)
    draft_m: float = Field(10.0, ge=1.0, le=30.0)
    weather_severity: int = Field(1, ge=0, le=2, description="0 = calm, 1 = moderate, 2 = rough.")
    route_type: str = "Transoceanic"
    maintenance_status: str = "Fair"


class PredictCurveRequest(BaseModel):
    """A speed sweep producing an admiralty consumption curve."""

    ship_types: list[Literal["container", "bulk", "tanker"]] = Field(
        default_factory=lambda: list(SHIP_TYPES)
    )
    speed_min: float = Field(8.0, ge=1.0, le=40.0)
    speed_max: float = Field(24.0, ge=1.0, le=40.0)
    points: int = Field(33, ge=3, le=200)
    draft_m: float = Field(10.0, ge=1.0, le=30.0)
    weather_severity: int = Field(1, ge=0, le=2)


class OptimizeRequest(BaseModel):
    """Configuration for a live QIEA + QPSO optimization run."""

    fuel_prices: dict[str, float] = Field(
        default_factory=lambda: {
            "HFO": 650.0,
            "LNG_DIESEL": 800.0,
            "MEOH_GREEN": 1200.0,
            "H2_GREEN": 3000.0,
            "NH3_GREEN": 2500.0,
        },
        description="Bunker price per metric ton for each optimizer fuel.",
    )
    carbon_price: float = Field(0.0, ge=0.0, le=500.0, description="Carbon price in $/t-CO2e.")
    pop_size: int = Field(50, ge=10, le=300, description="Q-bit population size.")
    generations: int = Field(50, ge=5, le=500, description="Generational search budget.")
    mutation_prob: float = Field(0.02, ge=0.0, le=0.5)
    lambda0: float = Field(10.0, ge=0.0, description="Initial constraint penalty weight.")
    archive_max: int = Field(100, ge=5, le=500)
    seed: int = Field(42, ge=0)

    def to_config(self) -> dict[str, Any]:
        """Translate the request into the optimizer's config dict."""
        import numpy as np

        prices = {fuel: float(self.fuel_prices.get(fuel, 0.0)) for fuel in OPTIMIZER_FUELS}
        missing = [f for f, v in prices.items() if v <= 0.0]
        if missing:
            raise ValueError(f"A positive price is required for every fuel; missing: {missing}")

        return {
            "pop_size": self.pop_size,
            "generations": self.generations,
            "theta_start": 0.05 * np.pi,
            "theta_end": 0.005 * np.pi,
            "mutation_prob": self.mutation_prob,
            "lambda0": self.lambda0,
            "fuel_prices": prices,
            "carbon_price": float(self.carbon_price),
            "archive_max": self.archive_max,
            "seed": self.seed,
        }
