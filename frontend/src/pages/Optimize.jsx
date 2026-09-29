import { useMemo, useState } from 'react'
import { IS_STATIC, api } from '../api/client'
import { recordedRun } from '../api/staticApi'
import { BarChart } from '../components/charts/BarChart'
import { Figure } from '../components/charts/Figure'
import { LineChart } from '../components/charts/LineChart'
import { ScatterChart } from '../components/charts/ScatterChart'
import { DataTable } from '../components/DataTable'
import { NumberField, Pill, SliderField } from '../components/Field'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { Disclosure, Panel } from '../components/Panel'
import { PlanTable } from '../components/PlanTable'
import { StatTile } from '../components/StatTile'
import { EmptyState, ErrorState } from '../components/States'
import { useOptimizationJob } from '../hooks/useOptimizationJob'
import { useResource } from '../hooks/useResource'
import { compact, fuelLabel, num, seconds, usd } from '../lib/format'
import { feasibilityInsight, hypervolumeInsight, mixInsight, paretoInsight } from '../lib/insights'
import { FUEL_ORDER, SERIES, fuelColor } from '../lib/palette'

const FUELS = [
  { code: 'HFO', min: 400, max: 1500, step: 25, initial: 650 },
  { code: 'LNG_DIESEL', min: 500, max: 1800, step: 25, initial: 800 },
  { code: 'MEOH_GREEN', min: 800, max: 2000, step: 25, initial: 1200 },
  { code: 'H2_GREEN', min: 2000, max: 4000, step: 50, initial: 3000 },
  { code: 'NH3_GREEN', min: 1500, max: 3500, step: 50, initial: 2500 },
]

const POP_SIZES = [20, 50, 100, 200]
const GENERATIONS = [20, 50, 100, 200, 300]

export default function Optimize() {
  const fleet = useResource(() => api.fleet(), [])
  const { job, error, starting, running, start, cancel } = useOptimizationJob()

  const [prices, setPrices] = useState(() =>
    Object.fromEntries(FUELS.map((f) => [f.code, f.initial])),
  )
  const [carbonPrice, setCarbonPrice] = useState(0)
  const [popIndex, setPopIndex] = useState(1)
  const [genIndex, setGenIndex] = useState(1)
  const [seed, setSeed] = useState(42)

  const popSize = POP_SIZES[popIndex]
  const generations = GENERATIONS[genIndex]

  const launch = () =>
    start({
      fuel_prices: prices,
      carbon_price: carbonPrice,
      pop_size: popSize,
      generations,
      seed,
      archive_max: 100,
    })

  // Without a backend there is no search to run, so the page presents a
  // recorded run of the real engine and says so, rather than faking progress.
  const shownJob = IS_STATIC ? recordedRun : job
  const result = shownJob?.status === 'done' ? shownJob.result : null

  return (
    <>
      <PageHeader
        title="Optimization engine"
        subtitle="QIEA rotation gates for assignment, fuel and shore power; QPSO for continuous cruising speeds"
        actions={
          <>
            {fleet.data && (
              <Pill>
                {fleet.data.totals.vessels} ships · {fleet.data.totals.routes} routes
              </Pill>
            )}
            {IS_STATIC ? (
              <button type="button" className="btn" disabled title="Needs the FastAPI backend">
                Run optimization
              </button>
            ) : running ? (
              <button type="button" className="btn btn--danger" onClick={cancel}>
                Cancel run
              </button>
            ) : (
              <button type="button" className="btn btn--primary" disabled={starting} onClick={launch}>
                {starting ? 'Starting…' : 'Run optimization'}
              </button>
            )}
          </>
        }
      />

      <div className="content">
        <div className="grid grid--sidebar-right">
          <Panel
            title="Search parameters"
            subtitle="Bunker prices and the carbon price set the objective weights; population and generations set the search budget"
          >
            <div className="grid grid--params" style={{ gap: 16 }}>
              <div className="stack">
                {FUELS.map((f) => (
                  <SliderField
                    key={f.code}
                    label={`${fuelLabel(f.code)} price`}
                    value={prices[f.code]}
                    display={`$${num(prices[f.code])}/t`}
                    min={f.min}
                    max={f.max}
                    step={f.step}
                    onChange={(v) => setPrices((p) => ({ ...p, [f.code]: v }))}
                  />
                ))}
              </div>
              <div className="stack">
                <SliderField
                  label="Carbon price"
                  value={carbonPrice}
                  display={`$${num(carbonPrice)}/t-CO₂e`}
                  min={0}
                  max={200}
                  step={5}
                  onChange={setCarbonPrice}
                  hint="Priced into the fuel-cost objective, so it shifts the whole front."
                />
                <SliderField
                  label="Population size (Q-bits)"
                  value={popIndex}
                  display={num(popSize)}
                  min={0}
                  max={POP_SIZES.length - 1}
                  onChange={setPopIndex}
                />
                <SliderField
                  label="Generations"
                  value={genIndex}
                  display={num(generations)}
                  min={0}
                  max={GENERATIONS.length - 1}
                  onChange={setGenIndex}
                  hint="300 generations at population 200 is the committed case-study budget (~6 min)."
                />
                <NumberField label="Random seed" value={seed} min={0} onChange={setSeed} />
              </div>
            </div>
          </Panel>

          <Panel
            title="Run status"
            subtitle={IS_STATIC ? 'A recorded run of the real engine' : 'Live progress from the search thread'}
          >
            <JobStatus job={shownJob} running={!IS_STATIC && running} error={IS_STATIC ? null : error} />
          </Panel>
        </div>

        {IS_STATIC && (
          <div className="note">
            <Icon name="info" size={18} className="note__icon" />
            <span>
              <strong>Recorded run.</strong> The search below is genuine output from the QIEA+QPSO
              engine — 50 generations at population 50, solved in{' '}
              {seconds(recordedRun?.elapsed_seconds)} — captured from the FastAPI backend. Running a
              new search executes NumPy in Python, so the controls are disabled in this published
              snapshot; start the backend with <code className="mono">make api</code> to drive the
              engine live.
            </span>
          </div>
        )}

        {!IS_STATIC && error && (
          <Panel>
            <ErrorState error={error} title="The optimization run failed" onRetry={launch} />
          </Panel>
        )}

        {!IS_STATIC && !job && !error && (
          <Panel>
            <EmptyState icon="cpu" title="No live run yet">
              Set the prices and search budget above, then run the engine. Pre-computed policy scenarios
              are on the Policy scenarios page if you would rather not wait.
            </EmptyState>
          </Panel>
        )}

        {result && <RunResult result={result} />}
      </div>
    </>
  )
}

/** Progress meter, generation counter and live search metrics. */
function JobStatus({ job, running, error }) {
  if (!job) {
    return <div className="muted">Idle — no run started in this session.</div>
  }

  const tone =
    job.status === 'done' ? 'good' : job.status === 'error' ? 'critical' : job.status === 'cancelled' ? 'warning' : 'neutral'

  return (
    <div className="stack">
      <div className="row-between">
        <Pill tone={tone}>{job.status}</Pill>
        <span className="mono muted">{job.job_id}</span>
      </div>

      <div>
        <div className="meter" role="progressbar" aria-valuenow={job.progress_pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="meter__fill" style={{ width: `${job.progress_pct}%` }} />
        </div>
        <div className="field__hint" style={{ marginTop: 5 }}>
          Generation {num(job.generation)} of {num(job.total_generations)} · {num(job.progress_pct, 1)}%
        </div>
      </div>

      <dl className="kv">
        <dt>Archive size</dt>
        <dd>{num(job.archive_size)}</dd>
        <dt>Hypervolume</dt>
        <dd>{num(job.hypervolume, 4)}</dd>
        <dt>Feasible individuals</dt>
        <dd>
          {num(job.feasible_count)}
          {job.population_size ? ` / ${num(job.population_size)}` : ''}
        </dd>
        <dt>Elapsed</dt>
        <dd>{seconds(job.elapsed_seconds)}</dd>
      </dl>

      {running && <div className="field__hint">Polling every 0.7 s — you can leave this page and come back.</div>}
      {job.status === 'cancelled' && (
        <div className="field__hint">Stopped at the generation boundary; no results were kept.</div>
      )}
      {error && <div className="field__hint">{error.message}</div>}
    </div>
  )
}

/** Results of a completed run: KPIs, front, convergence, fuel mix and plan. */
function RunResult({ result }) {
  const kpi = result.report?.kpi_deltas
  const mix = result.report?.fuel_mix_pct || {}
  const mixBars = FUEL_ORDER.filter((f) => mix[f] != null).map((f) => ({
    key: f,
    label: fuelLabel(f),
    value: mix[f],
    color: fuelColor(f),
  }))

  const paretoPoints = result.pareto.map((p) => ({
    id: p.solution_id,
    x: p.fuel_cost_usd,
    y: p.ghg_wtw_tco2e,
    highlight: p.is_knee,
    meta: [
      { label: 'OPEX', color: SERIES[3], value: usd(p.opex_usd) },
      { label: 'Deployments', color: SERIES[4], value: num(p.deployments_count) },
    ],
  }))

  const h = result.history
  const hvSeries = [
    {
      key: 'hv',
      label: 'Archive hypervolume',
      color: SERIES[0],
      points: h.generation.map((g, i) => ({ x: g, y: h.hypervolume[i] })),
    },
  ]
  const feasSeries = [
    {
      key: 'feasible',
      label: 'Feasible individuals',
      color: SERIES[2],
      points: h.generation.map((g, i) => ({ x: g, y: h.feasible_count[i] })),
    },
  ]

  // The report's per-vessel plan carries the BAU comparison for a live run.
  const plan = useMemo(
    () =>
      (result.report?.per_vessel_plan || []).map((row) => ({
        vessel_id: row.vessel_id,
        type: row.type,
        route_id: row.route_id,
        assigned: row.route_id !== 'Reserve' && row.route_id !== 'Unassigned',
        speed_kn: row.speed_kn,
        bau_speed_kn: row.bau_speed_kn,
        speed_delta_kn: Number((row.speed_kn - row.bau_speed_kn).toFixed(1)),
        fuel: row.fuel,
        shore_power: false,
        change_vs_bau: row.change_vs_bau,
      })),
    [result.report],
  )

  return (
    <div className="content">
      <div className="grid grid--kpi">
        <StatTile
          label="Fuel cost"
          value={usd(result.knee.objectives.fuel_cost_usd)}
          delta={kpi?.fuel_cost.delta_pct}
          deltaLabel="vs BAU"
          foot={kpi ? `BAU ${usd(kpi.fuel_cost.bau)}` : undefined}
        />
        <StatTile
          label="Well-to-wake CO₂e"
          value={compact(result.knee.objectives.ghg_wtw_tco2e)}
          unit="t"
          delta={kpi?.ghg_wtw.delta_pct}
          deltaLabel="vs BAU"
          foot={kpi ? `BAU ${compact(kpi.ghg_wtw.bau)} t` : undefined}
        />
        <StatTile
          label="Total OPEX"
          value={usd(result.knee.objectives.opex_usd)}
          delta={kpi?.opex.delta_pct}
          deltaLabel="vs BAU"
          foot={kpi ? `BAU ${usd(kpi.opex.bau)}` : undefined}
        />
        <StatTile
          label="Solved in"
          value={seconds(result.elapsed_seconds)}
          foot={`${num(result.pareto.length)} non-dominated solution${result.pareto.length === 1 ? '' : 's'} · carbon $${num(result.config.carbon_price)}/t`}
        />
      </div>

      <div className="grid grid--2">
        <Figure
          title="Pareto trade-off surface"
          subtitle="Fuel cost against lifecycle CO₂e; ★ marks the recommended (knee) plan"
          chart={
            <ScatterChart
              points={paretoPoints}
              height={300}
              xLabel="Fuel cost (USD)"
              yLabel="Well-to-wake CO₂e (t)"
              formatX={(v) => usd(v)}
              formatY={(v) => compact(v)}
              ariaLabel="Pareto solutions from this run"
            />
          }
          tableColumns={[
            { key: 'solution_id', label: 'Solution' },
            { key: 'fuel_cost_usd', label: 'Fuel cost', align: 'right', render: (r) => usd(r.fuel_cost_usd) },
            { key: 'ghg_wtw_tco2e', label: 'CO₂e (t)', align: 'right', render: (r) => num(r.ghg_wtw_tco2e) },
            { key: 'opex_usd', label: 'OPEX', align: 'right', render: (r) => usd(r.opex_usd) },
            { key: 'deployments_count', label: 'Deployments', align: 'right' },
            { key: 'is_knee', label: 'Recommended', render: (r) => (r.is_knee ? '★' : '') },
          ]}
          tableRows={result.pareto}
          tableCaption="Every non-dominated solution this run discovered."
          insight={paretoInsight(result.pareto)}
        />

        <Figure
          title="Fuel mix of the recommended plan"
          subtitle="Share of the fleet bunkering each fuel"
          chart={
            <BarChart
              bars={mixBars}
              formatValue={(v) => `${num(v, 0)}%`}
                  formatLabel={(v) => `${num(v, 1)}%`}
              ariaLabel="Share of the fleet per fuel"
            />
          }
          tableColumns={[
            { key: 'label', label: 'Fuel' },
            { key: 'value', label: 'Share', align: 'right', render: (r) => `${num(r.value, 1)}%` },
          ]}
          tableRows={mixBars}
          tableCaption="Fuel mix of the recommended plan."
          insight={mixInsight(mixBars)}
        />
      </div>

      <div className="grid grid--2">
        <Figure
          title="Convergence — archive quality"
          subtitle="Hypervolume of the non-dominated archive per generation"
          chart={
            <LineChart
              series={hvSeries}
              height={220}
              xLabel="Generation"
              yLabel="Hypervolume"
              formatX={(v) => num(v)}
              formatY={(v) => num(v, 2)}
              formatValue={(v) => num(v, 4)}
              labelLast
              ariaLabel="Archive hypervolume against generation"
            />
          }
          insight={hypervolumeInsight(h)}
        />
        <Figure
          title="Convergence — feasibility"
          subtitle="Individuals satisfying every hard constraint after greedy repair"
          chart={
            <LineChart
              series={feasSeries}
              height={220}
              xLabel="Generation"
              yLabel="Feasible individuals"
              formatX={(v) => num(v)}
              formatY={(v) => num(v)}
              labelLast
              zeroBase
              ariaLabel="Feasible population count against generation"
            />
          }
          insight={feasibilityInsight(h, result.config?.pop_size)}
        />
      </div>

      <Disclosure
        title="Recommended deployment"
        subtitle={`${num(result.knee.assignments.length)} vessel–route deployments · ${
          result.knee.feasible ? 'all constraints satisfied' : 'constraint violations remain'
        }`}
        count={`${plan.length} vessels`}
        defaultOpen
      >
        <PlanTable plan={plan} caption="Rows that differ from business-as-usual are highlighted." />
      </Disclosure>

      <Disclosure
        title="Deployment detail"
        subtitle="every vessel–route leg with its speed and bunker fuel"
        count={`${result.knee.assignments.length} legs`}
      >
        <DataTable
          columns={[
            { key: 'vessel_id', label: 'Vessel' },
            { key: 'route_id', label: 'Route' },
            { key: 'speed_kn', label: 'Speed kn', align: 'right', render: (r) => num(r.speed_kn, 2) },
            { key: 'fuel', label: 'Fuel', render: (r) => fuelLabel(r.fuel) },
            {
              key: 'shore_power',
              label: 'Shore power',
              render: (r) => (r.shore_power ? <span className="tag">connected</span> : <span className="muted">—</span>),
            },
          ]}
          rows={result.knee.assignments}
          rowKey={(r, i) => `${r.vessel_id}-${r.route_id}-${i}`}
          tall
        />
      </Disclosure>
    </div>
  )
}
