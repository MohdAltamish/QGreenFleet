/**
 * One-sentence takeaways under each chart, computed from the same data the
 * chart draws — the line that turns a plot into a finding. Shared by the live
 * run (Optimize) and the pre-computed scenarios.
 */
import { compact, num, usd } from './format'

export function paretoInsight(pareto) {
  if (!pareto?.length) return null
  if (pareto.length === 1) return 'The archive holds a single solution, so there is no trade-off to choose along.'
  const knee = pareto.find((p) => p.is_knee) || pareto[0]
  const costs = pareto.map((p) => p.fuel_cost_usd)
  return `The recommended plan costs ${usd(knee.fuel_cost_usd)} for ${compact(knee.ghg_wtw_tco2e)} t CO₂e; the ${pareto.length} options span ${usd(Math.min(...costs))}–${usd(Math.max(...costs))} in fuel cost.`
}

export function mixInsight(bars) {
  if (!bars?.length) return null
  const [top] = [...bars].sort((a, b) => b.value - a.value)
  return `${top.label} dominates at ${num(top.value, 1)}% of the fleet${bars.length > 1 ? `, across ${bars.length} fuels in use` : ''}.`
}

export function hypervolumeInsight(history) {
  const hv = history?.hypervolume
  if (!hv?.length) return null
  const final = hv[hv.length - 1]
  const peak = Math.max(...hv)
  const peakGen = history.generation[hv.indexOf(peak)]
  // Report end and peak rather than claiming convergence: archive HV can oscillate.
  return final >= peak * 0.99
    ? `Hypervolume ends at its peak of ${num(final, 3)}, first reached at generation ${num(peakGen)}.`
    : `Hypervolume ends at ${num(final, 3)}, below its peak of ${num(peak, 3)} at generation ${num(peakGen)} — the archive did not hold its best coverage.`
}

export function feasibilityInsight(history, populationSize) {
  const f = history?.feasible_count
  if (!f?.length) return null
  const final = f[f.length - 1]
  return `${num(final)}${populationSize ? ` of ${num(populationSize)}` : ''} individuals end the search feasible after repair.`
}
