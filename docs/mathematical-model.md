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
FC[v,r] = ƒ_pred(v, s[v,r], load[v,r], weather_r) · (D_r / (24·s[v,r]))   [tons/voyage]

## Objectives (minimize)
Z1 (fuel cost)  = Σ_{v,r} x[v,r] · FC[v,r] · price_{f[v]}
Z2 (GHG, tCO2e) = Σ_{v,r} x[v,r] · FC[v,r] · LHV_{f[v]} · EF_{f[v]} · 10⁻⁶  −  shore-power savings Σ sp[v,p]·SP_save
Z3 (opex)       = Z1 + Σ_v charter_v · days_v + Σ_r port_costs + carbon_price · Z2

## Constraints
C1 Demand:      Σ_v x[v,r] · cap_v ≥ Q_r            ∀r
C2 Schedule:    D_r / s[v,r] ≤ T_r  if x[v,r]=1      ∀v,r
C3 Assignment:  Σ_r x[v,r] · voyage_days[v,r] ≤ available_days_v   ∀v
C4 Emissions:   attained_CII_v ≤ CII_limit_v         ∀v
                where attained_CII_v = (annual CO₂_v · 10⁶) / (DWT_v · annual_distance_v)
C5 Fuel avail.: f[v]=g only if fuel g bunkerable on v's assigned ports
C6 Speed:       Vmin_v ≤ s[v,r] ≤ Vmax_v

## Handling
- C1: greedy repair (add cheapest feasible vessel)
- C2, C6: clip speeds to feasible interval
- C4, C5: adaptive penalty added to all objectives: penalty = λ_g · Σ violations, λ_g grows with generation
