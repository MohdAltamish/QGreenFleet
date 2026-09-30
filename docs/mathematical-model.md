# Mathematical Model

## Sets
V vessels, R routes, F fuels {HFO,LNG,MeOH,H2,NH3}, P ports

## Parameters
D_r distance (nm); T_r schedule window (h); Q_r demand (TEU); cap_v capacity;
price_f ($/t); EF_f WtW factor (gCO2e/MJ); LHV_f (MJ/kg); CII_limit_v;
charter_v ($/day); Vmin_v, Vmax_v

## Decision variables
x[v,r] ∈ {0,1}   vessel v serves route r
s[v,r] ∈ [Vmin, Vmax]   speed (kn)
f[v] ∈ F   fuel type of vessel v
sp[v,p] ∈ {0,1}   shore power at port p

## Fuel consumption (from prediction model)
FC[v,r] = ƒ_pred(v, s[v,r], draft, weather_r) · (D_r / (24·s[v,r]))   [HFO-equivalent tons/voyage]
FC_f[v,r] = FC[v,r] · LHV_HFO / LHV_{f[v]}   [tons of the chosen fuel; energy basis]
ƒ_pred = MRV QPSO-XGBoost level × admiralty speed law (∝ v³, part-load SFOC penalty) × rule-based draft and weather factors.
In Z1/Z2 below, FC means FC_f (fuel mass after LHV conversion).

## Objectives (minimize)
Z1 (fuel cost)  = Σ_{v,r} x[v,r] · FC[v,r] · price_{f[v]}
Z2 (GHG, tCO2e) = Σ_{v,r} x[v,r] · FC[v,r] · LHV_{f[v]} · EF_{f[v]} · 10⁻⁶  −  shore-power savings Σ sp[v,p]·SP_save  (SP_save = 3 tCO2e in code)
Z3 (opex)       = Z1 + Σ_v charter_v · days_v + Σ_r port_costs + carbon_price · Z2

## Constraints
C1 Demand:      Σ_v x[v,r] · cap_v ≥ Q_r            ∀r
C2 Schedule:    D_r / s[v,r] ≤ T_r  if x[v,r]=1      ∀v,r
C3 Assignment:  Σ_r x[v,r] ≤ 1   ∀v   (implemented as one route per vessel per planning period, i.e. available_days_v = one route schedule window)
C4 Emissions:   attained_CII_v ≤ CII_limit_v         ∀v
                where attained_CII_v = (CO₂_v · 10⁶) / (DWT_v · distance_v), with CO₂_v from the vessel's
                assigned speed(s) and fuel: fuel_kg = Σ D_r · fuel_per_nm_v · (s[v,r]/design_v)² · LHV_HFO/LHV_{f[v]}
C5 Fuel avail.: f[v]=g only if fuel g bunkerable on v's assigned ports
C6 Speed:       Vmin_v ≤ s[v,r] ≤ Vmax_v

## Handling
- C1: greedy repair (add cheapest feasible vessel)
- C3: repair keeps at most one route per vessel
- C2, C6: clip speeds to feasible interval
- C4, C5: adaptive penalty added to all objectives: penalty = λ_g · Σ violations, λ_g grows with generation
