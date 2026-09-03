"""
Fuel emission factors library for QGreenFleet.

Provides Tank-to-Wake (TtW), Well-to-Tank (WtT), and Well-to-Wake (WtW)
greenhouse gas emission factors in g-CO2e/MJ for all supported marine fuels.

Sources:
    - Carbon factors (Cf), CH4/N2O baselines, WtT ranges:
      IMO Fourth GHG Study 2020.
    - Green fuel (H2, NH3, e-/bio-methanol) WtT defaults:
      FuelEU Maritime Regulation (EU) 2023/1805, Annex II (RFNBO pathways).
    - GWP100 values: IPCC AR5 (CH4 = 28, N2O = 265).
    - LHV values: standard marine engineering references
      (ISO 8217 / MAN Energy Solutions engine data).

Units convention:
    lhv       : MJ/kg (lower heating value)
    cf        : g-CO2 per g-fuel (tank-to-wake combustion CO2)
    ch4, n2o  : g per g-fuel (tank-to-wake non-CO2 GHG baselines)
    wtt_gpg   : g-CO2e per g-fuel (upstream, well-to-tank)
    All public functions return g-CO2e per MJ of fuel energy.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Global warming potentials (100-year horizon, IPCC AR5)
# ---------------------------------------------------------------------------
GWP_CH4: float = 28.0
GWP_N2O: float = 265.0

# ---------------------------------------------------------------------------
# Fuel factor database
# ---------------------------------------------------------------------------
FUEL_FACTORS: dict[str, dict[str, float]] = {
    # ------------------------- Conventional fossil -------------------------
    "HFO": {          # ISO 8217 RME-RMK
        "lhv": 40.2, "cf": 3.114, "ch4": 0.00006, "n2o": 0.00016,
        "wtt_gpg": 0.400,   # midpoint of IMO range 0.350-0.450
    },
    "LFO": {          # ISO 8217 RMA-RMD
        "lhv": 41.0, "cf": 3.151, "ch4": 0.00006, "n2o": 0.00016,
        "wtt_gpg": 0.400,
    },
    "MGO": {          # ISO 8217 DMX-DMB (marine diesel / gas oil)
        "lhv": 42.7, "cf": 3.206, "ch4": 0.00006, "n2o": 0.00016,
        "wtt_gpg": 0.590,   # midpoint of IMO range 0.530-0.650
    },
    # ------------------------------ LNG ------------------------------------
    # Methane slip depends on engine cycle -> two entries.
    "LNG_OTTO": {     # dual-fuel Otto cycle, low pressure (high slip)
        "lhv": 48.0, "cf": 2.750, "ch4": 0.0155, "n2o": 0.00011,
        "wtt_gpg": 0.875,   # midpoint of IMO range 0.650-1.100
    },
    "LNG_DIESEL": {   # dual-fuel Diesel cycle, high pressure (low slip)
        "lhv": 48.0, "cf": 2.750, "ch4": 0.0011, "n2o": 0.00004,
        "wtt_gpg": 0.875,
    },
    # ----------------------------- Methanol --------------------------------
    "MEOH_GREY": {    # fossil (natural-gas based) methanol
        "lhv": 19.9, "cf": 1.375, "ch4": 0.0, "n2o": 0.0,
        "wtt_gpg": 0.925,   # midpoint of IMO range 0.800-1.050
    },
    "MEOH_GREEN": {   # bio-/e-methanol: biogenic carbon offsets TtW CO2.
        # Modelled with negative WtT so that net WtW ~= 10 g-CO2e/MJ
        # (FuelEU Annex II RFNBO treatment).
        "lhv": 19.9, "cf": 1.375, "ch4": 0.0, "n2o": 0.0,
        "wtt_gpg": -1.176,
    },
    # --------------------------- Zero-carbon TtW ---------------------------
    "H2_GREEN": {     # electrolytic hydrogen, renewable electricity
        "lhv": 120.0, "cf": 0.0, "ch4": 0.0, "n2o": 0.0,
        "wtt_gpg": 1.200,   # ~10 g-CO2e/MJ upstream
    },
    "NH3_GREEN": {    # green ammonia (Haber-Bosch from green H2)
        # N2O combustion guard value can be added once engine data matures.
        "lhv": 18.6, "cf": 0.0, "ch4": 0.0, "n2o": 0.0,
        "wtt_gpg": 0.223,   # ~12 g-CO2e/MJ upstream
    },
}

# Fuels selectable by the optimizer (decision variable domain F).
OPTIMIZER_FUELS: tuple[str, ...] = (
    "HFO", "LNG_DIESEL", "MEOH_GREEN", "H2_GREEN", "NH3_GREEN",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _get(fuel: str) -> dict[str, float]:
    try:
        return FUEL_FACTORS[fuel]
    except KeyError:
        raise ValueError(
            f"Unknown fuel '{fuel}'. Available: {sorted(FUEL_FACTORS)}"
        ) from None


def lhv_mj_per_kg(fuel: str) -> float:
    """Lower heating value of *fuel* in MJ/kg."""
    return _get(fuel)["lhv"]


def ttw_gco2e_per_mj(fuel: str) -> float:
    """Tank-to-Wake GHG intensity in g-CO2e per MJ (CO2 + CH4 + N2O, GWP100)."""
    f = _get(fuel)
    gpg = f["cf"] + GWP_CH4 * f["ch4"] + GWP_N2O * f["n2o"]  # g-CO2e / g-fuel
    return gpg / (f["lhv"] / 1000.0)                          # -> per MJ


def wtt_gco2e_per_mj(fuel: str) -> float:
    """Well-to-Tank (upstream) GHG intensity in g-CO2e per MJ."""
    f = _get(fuel)
    return f["wtt_gpg"] / (f["lhv"] / 1000.0)


def wtw_gco2e_per_mj(fuel: str) -> float:
    """Well-to-Wake GHG intensity in g-CO2e per MJ (WtT + TtW)."""
    return ttw_gco2e_per_mj(fuel) + wtt_gco2e_per_mj(fuel)


def voyage_ghg_tco2e(fuel: str, fuel_tons: float) -> float:
    """Total WtW GHG for burning *fuel_tons* tonnes of *fuel*, in t-CO2e.

    tonnes -> kg -> MJ (via LHV) -> g-CO2e (via WtW factor) -> t-CO2e.
    """
    if fuel_tons < 0:
        raise ValueError("fuel_tons must be non-negative")
    energy_mj = fuel_tons * 1000.0 * lhv_mj_per_kg(fuel)
    return energy_mj * wtw_gco2e_per_mj(fuel) / 1e6


def ttw_co2_tons(fuel: str, fuel_tons: float) -> float:
    """Tank-to-Wake CO2 only (no CH4/N2O), in tonnes.

    This is the quantity used by the IMO CII calculation and EU ETS,
    which are CO2-based rather than CO2e-based.
    """
    if fuel_tons < 0:
        raise ValueError("fuel_tons must be non-negative")
    return fuel_tons * _get(fuel)["cf"]


def summary_table() -> list[dict[str, float | str]]:
    """Return TtW/WtT/WtW per fuel — used by the UI emissions page and docs."""
    return [
        {
            "fuel": name,
            "lhv_mj_kg": f["lhv"],
            "ttw_g_mj": round(ttw_gco2e_per_mj(name), 1),
            "wtt_g_mj": round(wtt_gco2e_per_mj(name), 1),
            "wtw_g_mj": round(wtw_gco2e_per_mj(name), 1),
        }
        for name, f in FUEL_FACTORS.items()
    ]


if __name__ == "__main__":
    for row in summary_table():
        print(row)
