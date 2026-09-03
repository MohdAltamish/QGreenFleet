# Quantum-Inspired Algorithms

## 1. QIEA (discrete decisions: x[v,r], f[v], sp[v,p])

### Q-bit encoding
Each binary decision = qubit (α, β), α²+β²=1. P(bit=1)=β².
Individual = Q-matrix over all binary vars. Fuel type = one-hot block of |F| qubits (repair to single 1).

### Loop (per generation)
1. Observe: sample binary solution from each Q-individual
2. Repair: demand (C1), fuel one-hot, fuel availability (C5)
3. Evaluate Z1..Z3 with penalties (C4)
4. Nondominated sort + crowding → update external archive
5. Rotation gate update, per qubit, toward a randomly chosen archive leader b:
   Δθ_i = θ_base · direction(bit_i, b_i, dominated?)  (lookup table, Han & Kim 2002)
   [α';β'] = [[cosΔθ, −sinΔθ],[sinΔθ, cosΔθ]] · [α;β]
   θ_base: 0.05π → 0.005π (linear decay)
6. Quantum mutation: with p=0.02, reset qubit to (1/√2, 1/√2)
7. Migration every 25 gens: reseed worst 10% from archive

## 2. QPSO (continuous speeds s[v,r])
mbest = mean of all personal bests
p_i = φ·pbest_i + (1−φ)·leader,  φ~U(0,1); leader from archive (crowding-selected)
x_i = p_i ± β · |mbest − x_i| · ln(1/u),  u~U(0,1)
β: 1.0 → 0.4 (linear). Clip to [Vmin, Vmax] and schedule-feasible speed D_r/T_r.

## 3. Hybrid coupling
One solution = (Q-matrix, speed vector). Each generation: QIEA step for Q, QPSO step for speeds,
joint evaluation. Archive shared. Stopping: 300 gens or 30 gens without hypervolume improvement.

## 4. Prediction-side quantum inspiration
- **QPSO-XGB:** QPSO searches XGB hyperparameters + binary feature mask (qubit-encoded)
- **QiNN:** neurons hold angle θ; output = sin²(θ + Σw·x); gradient-trained (PyTorch)

## 5. Complexity
Per generation: O(pop · (V·R eval + V·R·log for sort)). 200 vessels × 20 routes × pop 200 ≈ ms-scale per gen with vectorized NumPy.

## 6. Pseudocode
```
init Q-population, speeds; archive = ∅
for g in 1..G:
    S = observe(Q); repair(S)
    F = evaluate(S, speeds, predictor)
    archive = pareto_update(archive, S)
    Q = rotation_update(Q, archive, θ(g)); mutate(Q)
    speeds = qpso_update(speeds, pbest, archive, β(g))
return archive
```
