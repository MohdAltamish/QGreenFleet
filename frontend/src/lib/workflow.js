/**
 * The decision pipeline the app walks through: INPUT → PROCESSING → ANALYSIS
 * → VALIDATION → RESULT. Each step maps onto existing routes, and its state is
 * read off the real /health payload — never simulated.
 */
export const STEPS = [
  {
    key: 'input',
    stage: 'Input',
    title: 'Fleet & routes',
    description: 'Load the vessel catalogue and route corridors',
    icon: 'ship',
    routes: ['/fleet'],
    done: (h) => Boolean(h?.fleet?.loaded),
    failed: (h) => !h || h.fleet?.loaded === false,
  },
  {
    key: 'processing',
    stage: 'Processing',
    title: 'Fuel surrogate',
    description: 'Predict burn across speed, draft and sea state',
    icon: 'activity',
    routes: ['/predict'],
    done: (h) => Boolean(h?.predictor?.available),
    failed: (h) => h?.predictor?.available === false,
  },
  {
    key: 'analysis',
    stage: 'Analysis',
    title: 'Optimisation',
    description: 'QIEA + QPSO search over deployment, fuel and speed',
    icon: 'cpu',
    routes: ['/optimize'],
    done: (h) => (h?.scenarios?.length ?? 0) > 0,
    failed: () => false,
  },
  {
    key: 'validation',
    stage: 'Validation',
    title: 'Scenarios & benchmarks',
    description: 'Stress-test against policy and rival algorithms',
    icon: 'target',
    routes: ['/scenarios', '/benchmark'],
    done: (h) => Boolean(h?.artifacts?.benchmark_results && h?.artifacts?.carbon_sweep),
    failed: () => false,
  },
  {
    key: 'result',
    stage: 'Result',
    title: 'Decision reports',
    description: 'Export the evidence for the decision-maker',
    icon: 'file',
    routes: ['/reports'],
    done: (h) => Boolean(h?.artifacts?.executive_summary_pdf || h?.artifacts?.technical_report_pdf),
    failed: () => false,
  },
]

export const STATUS_LABEL = { completed: 'Completed', active: 'Active', upcoming: 'Upcoming', error: 'Error' }

/**
 * Resolve every step to completed | active | upcoming | error.
 *
 * The step owning the current route is active (an error still wins, so a
 * broken step is never dressed up as in-progress). Off-pipeline routes such as
 * the overview mark the first unfinished step active instead.
 */
export function resolveSteps(health, pathname, { pending = false } = {}) {
  const routeIndex = STEPS.findIndex((s) => s.routes.includes(pathname))
  const firstOpen = STEPS.findIndex((s) => !s.done(health))
  const activeIndex = routeIndex >= 0 ? routeIndex : firstOpen
  return STEPS.map((step, i) => {
    let status = step.done(health) ? 'completed' : 'upcoming'
    if (i === activeIndex) status = 'active'
    // While /health is in flight nothing is known yet, so nothing has failed.
    if (!pending && step.failed(health)) status = 'error'
    return { ...step, index: i, status }
  })
}
