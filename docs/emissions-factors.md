# Emissions Factors & Regulatory Library

## WtW factors (populate from IMO 4th GHG Study / FuelEU — indicative placeholders)
| Fuel | LHV (MJ/kg) | TtW gCO2e/MJ | WtT gCO2e/MJ | WtW gCO2e/MJ |
|---|---|---|---|---|
| HFO | 40.2 | ~78 | ~14 | ~92 |
| MGO | 42.7 | ~75 | ~14 | ~89 |
| LNG (Otto MS) | 48.0 | ~58 + slip | ~18 | ~76 |
| Methanol (grey) | 19.9 | ~69 | ~31 | ~100 |
| Methanol (green) | 19.9 | ~69 (biogenic offset) | — | ~10 |
| H2 (green) | 120.0 | 0 | ~10 | ~10 |
| NH3 (green) | 18.6 | 0 (+N2O guard) | ~12 | ~12 |
> ACTION: replace with cited exact values before demo; keep source column.

## CII (IMO)
attained = annual CO₂ (g) / (DWT × annual nm). Bands A–E vs reference line, reduction factor per year (2023: 5%, tightening annually). In code (`src/optimization/constraints.py`) the constraint is attained CII ≤ `cii_limit` per vessel (default 1984·DWT^−0.489), using the vessel's speed and fuel; the cii_tightened scenario lowers the limit by 11%.

## EU ETS / FuelEU (scenario module)
- Carbon price ($/t) is multiplied by total WtW GHG and added to opex (Z3) for all voyages (no EU-only scope)
- FuelEU: WtW intensity limit vs 2020 baseline: −2% (2025), −6% (2030) — not implemented as a scenario toggle; FuelEU is used only as a source for factors

## Shore power
In code: each assigned vessel–route with sp=1 on a route flagged `shore_power` gets a flat 3 tCO₂e reduction in Z2 (`src/optimization/objectives.py`). There is no shore-power-availability scenario lever.
