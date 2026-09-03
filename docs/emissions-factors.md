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
attained = annual CO₂ (g) / (DWT × annual nm). Bands A–E vs reference line, reduction factor per year (2023: 5%, tightening annually). Constraint: band ≤ C.

## EU ETS / FuelEU (scenario module)
- Carbon price applied to TtW CO₂e for EU voyages (scenario slider 0–200 $/t)
- FuelEU: WtW intensity limit vs 2020 baseline: −2% (2025), −6% (2030) — scenario toggle

## Shore power
While berthed with sp=1: auxiliary fuel burn (≈2–4 t/day HFO-equiv) replaced by grid electricity at grid EF (scenario parameter).
