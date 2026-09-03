"""Validate emission factor computations against hand-checked values."""
import pytest

from src.emissions.factors import (
    FUEL_FACTORS, summary_table, ttw_gco2e_per_mj,
    voyage_ghg_tco2e, ttw_co2_tons, wtw_gco2e_per_mj,
)

# Hand-computed expected WtW values (g-CO2e/MJ), tolerance +/-2%
EXPECTED_WTW = {
    "HFO": 88.5, "MGO": 89.9, "LNG_OTTO": 85.1,
    "LNG_DIESEL": 76.1, "MEOH_GREY": 115.7,
}

@pytest.mark.parametrize("fuel,expected", EXPECTED_WTW.items())
def test_wtw_matches_hand_calc(fuel, expected):
    assert wtw_gco2e_per_mj(fuel) == pytest.approx(expected, rel=0.02)

def test_lng_otto_slip_penalty():
    # Methane slip must make Otto-cycle LNG worse than Diesel-cycle LNG
    assert wtw_gco2e_per_mj("LNG_OTTO") > wtw_gco2e_per_mj("LNG_DIESEL")

def test_green_fuels_below_15():
    for fuel in ("MEOH_GREEN", "H2_GREEN", "NH3_GREEN"):
        assert wtw_gco2e_per_mj(fuel) < 15.0

def test_voyage_ghg_hfo():
    # 100 t HFO: 100*1000 kg * 40.2 MJ/kg * 88.5 g/MJ / 1e6 = ~355.8 tCO2e
    assert voyage_ghg_tco2e("HFO", 100) == pytest.approx(355.8, rel=0.02)

def test_ttw_co2_uses_cf_only():
    assert ttw_co2_tons("HFO", 100) == pytest.approx(311.4, rel=0.001)

def test_unknown_fuel_raises():
    with pytest.raises(ValueError):
        ttw_gco2e_per_mj("COAL")
