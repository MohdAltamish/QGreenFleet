import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { BarChart } from '../components/charts/BarChart'
import { Figure } from '../components/charts/Figure'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { Panel } from '../components/Panel'
import { StatTile } from '../components/StatTile'
import { ErrorState, Loader } from '../components/States'
import { Workflow } from '../components/Workflow'
import { useResource } from '../hooks/useResource'
import { compact, fuelLabel, num, pct, seconds, usd } from '../lib/format'
import { FUEL_ORDER, fuelColor } from '../lib/palette'
import { resolveSteps } from '../lib/workflow'

const TITLE = 'Fleet decarbonisation overview'
const SUBTITLE = 'Quantum-inspired deployment, speed and fuel decisions for the active fleet'

export default function Overview({ health }) {
  const overview = useResource(() => api.overview(), [])
  const status = healthStatus(health)

  if (overview.loading) {
    return (
      <>
        <PageHeader title={TITLE} subtitle={SUBTITLE} status={status} />
        <Loader label="Loading platform status…" />
      </>
    )
  }

  if (overview.error && !overview.data) {
    return (
      <>
        <PageHeader title={TITLE} subtitle={SUBTITLE} status={status} />
        <Panel>
          <ErrorState error={overview.error} onRetry={overview.reload} />
        </Panel>
      </>
    )
  }

  const data = overview.data
  const baseline = data.baseline
  const deltas = baseline?.deltas
  const mix = baseline?.fuel_mix_pct || {}
  const mixBars = FUEL_ORDER.filter((f) => mix[f] != null).map((f) => ({
    key: f,
    label: fuelLabel(f),
    value: mix[f],
    color: fuelColor(f),
  }))
  const steps = resolveSteps(health?.data, '/overview', { pending: health?.loading })
  const topFuel = [...mixBars].sort((a, b) => b.value - a.value)[0]

  return (
    <>
      <PageHeader
        title={TITLE}
        subtitle={SUBTITLE}
        status={status}
        actions={
          <Link className="btn btn--primary" to="/optimize">
            <Icon name="play" size={15} />
            Run optimization
          </Link>
        }
      />

      <Verdict baseline={baseline} mixBars={mixBars} predictor={health?.data?.predictor} />

      <div className="grid grid--kpi">
        <StatTile
          label="Active fleet"
          value={num(data.fleet_size)}
          unit="ships"
          foot={`${num(data.routes_count)} commercial routes`}
        />
        <StatTile
          label="Fuel cost — recommended plan"
          value={deltas ? usd(deltas.fuel_cost.opt) : '—'}
          delta={deltas?.fuel_cost.delta_pct}
          deltaLabel="vs business-as-usual"
          goodDirection="down"
          foot={deltas ? `BAU ${usd(deltas.fuel_cost.bau)}` : 'Run a scenario to populate'}
        />
        <StatTile
          label="Lifecycle CO₂e — recommended plan"
          value={deltas ? compact(deltas.ghg_wtw.opt) : '—'}
          unit="t"
          delta={deltas?.ghg_wtw.delta_pct}
          deltaLabel="vs business-as-usual"
          goodDirection="down"
          foot={deltas ? `BAU ${compact(deltas.ghg_wtw.bau)} t well-to-wake` : undefined}
        />
        <StatTile
          label="Total OPEX — recommended plan"
          value={deltas ? usd(deltas.opex.opt) : '—'}
          delta={deltas?.opex.delta_pct}
          deltaLabel="vs business-as-usual"
          goodDirection="down"
          foot={deltas ? `BAU ${usd(deltas.opex.bau)}` : undefined}
        />
      </div>

      <section className="section">
        <div className="section-head">
          <h2 className="section-head__title">Decision pipeline</h2>
          <span className="section-head__note">
            Five steps from fleet data to a defensible recommendation. Select a step to open it.
          </span>
        </div>
        <Workflow steps={steps} />
      </section>

      <div className="grid grid--main-aside">
        {mixBars.length > 0 ? (
          <Figure
            title="Fuel mix of the recommended plan"
            subtitle="Share of deployed vessels bunkering each fuel, baseline scenario"
            chart={
              <BarChart
                bars={mixBars}
                formatValue={(v) => `${num(v, 0)}%`}
                formatLabel={(v) => `${num(v, 1)}%`}
                ariaLabel="Share of deployed vessels per fuel"
              />
            }
            tableColumns={[
              { key: 'label', label: 'Fuel' },
              { key: 'value', label: 'Share of deployed ships', align: 'right', render: (r) => `${num(r.value, 1)}%` },
            ]}
            tableRows={mixBars}
            tableCaption="Fuel mix of the baseline scenario's recommended plan."
            insight={
              topFuel &&
              `${topFuel.label} still carries ${num(topFuel.value, 1)}% of deployed ships; ${
                mix.MEOH_GREEN != null
                  ? `green methanol reaches ${num(mix.MEOH_GREEN, 1)}%.`
                  : 'no ship switches to green methanol.'
              }`
            }
          />
        ) : (
          <Panel title="Fuel mix of the recommended plan">
            <div className="states">Run the baseline scenario to populate the fuel mix.</div>
          </Panel>
        )}

        <Panel title="System characteristics" subtitle="What this deployment can currently do">
          <dl className="kv">
            <dt>Surrogate model</dt>
            <dd className="mono">{data.predictor?.model_name || '—'}</dd>
            <dt>Prediction stages</dt>
            <dd>{data.predictor?.two_stage ? 'MRV macro + voyage micro' : 'Single stage'}</dd>
            <dt>Pre-computed scenarios</dt>
            <dd className="mono">{data.scenarios.length}</dd>
            <dt>Pareto solutions (baseline)</dt>
            <dd className="mono">{baseline ? num(baseline.pareto_size) : '—'}</dd>
            <dt>Baseline solve time</dt>
            <dd className="mono">{baseline?.elapsed_seconds ? seconds(baseline.elapsed_seconds) : '—'}</dd>
            <dt>QIEA wall-clock vs GA</dt>
            <dd className="mono">{data.optimizer_speedup_vs_ga ? `${data.optimizer_speedup_vs_ga}× faster` : '—'}</dd>
            <dt>Optimizer fuels</dt>
            <dd>{data.fuels.map(fuelLabel).join(', ')}</dd>
          </dl>
        </Panel>
      </div>
    </>
  )
}

function healthStatus(health) {
  if (health?.loading) return { tone: 'info', label: 'Checking API' }
  if (!health?.data) return { tone: 'critical', label: 'API offline' }
  return health.data.status === 'ok'
    ? { tone: 'good', label: 'All systems operational' }
    : { tone: 'warning', label: 'Degraded — surrogate offline' }
}

/**
 * The focal point: what the system concluded, how far to trust it, and why it
 * matters. The committed baseline scores worse than BAU on all three
 * objectives — BAU meets demand with far fewer deployed ships — so the verdict
 * says so plainly rather than presenting the deltas as savings.
 */
function Verdict({ baseline, mixBars, predictor }) {
  if (!baseline) {
    return (
      <section className="verdict" aria-labelledby="verdict-title">
        <div>
          <span className="verdict__eyebrow">
            <Icon name="target" size={15} />
            What the system determined
          </span>
          <h2 id="verdict-title" className="verdict__headline">
            No recommendation yet
          </h2>
          <p className="verdict__why">
            The baseline scenario has not been solved on this deployment, so there is no plan to report.
          </p>
          <div className="verdict__actions">
            <Link className="btn btn--primary" to="/optimize">
              Run the engine
            </Link>
          </div>
        </div>
      </section>
    )
  }

  const d = baseline.deltas
  const worseEverywhere = d.fuel_cost.delta_pct > 0 && d.ghg_wtw.delta_pct > 0 && d.opex.delta_pct > 0
  const betterEverywhere = d.fuel_cost.delta_pct < 0 && d.ghg_wtw.delta_pct < 0 && d.opex.delta_pct < 0
  const ranked = [...mixBars].sort((a, b) => b.value - a.value)

  return (
    <section className="verdict" aria-labelledby="verdict-title">
      <div>
        <span className="verdict__eyebrow">
          <Icon name="target" size={15} />
          What the system determined · baseline scenario
        </span>
        <h2 id="verdict-title" className="verdict__headline">
          Recommended plan:{' '}
          {ranked.map((b, i) => (
            <span key={b.key}>
              <span className="verdict__mix">
                {num(b.value, 1)}% {b.label}
              </span>
              {i < ranked.length - 2 ? ', ' : i === ranked.length - 2 ? ' and ' : ''}
            </span>
          ))}
        </h2>
        <p className="verdict__why">
          {worseEverywhere ? (
            <>
              <strong>This is not a saving against business-as-usual.</strong> The plan costs{' '}
              {pct(d.fuel_cost.delta_pct)} in fuel and emits {pct(d.ghg_wtw.delta_pct)} CO₂e against BAU,
              because BAU meets route demand with a handful of large ships and leaves the rest idle — a
              cheaper but much smaller deployment, so the two are not like-for-like.
            </>
          ) : betterEverywhere ? (
            <>
              <strong>It improves on business-as-usual on every objective:</strong> fuel cost{' '}
              {pct(d.fuel_cost.delta_pct)}, CO₂e {pct(d.ghg_wtw.delta_pct)}, OPEX {pct(d.opex.delta_pct)}.
            </>
          ) : (
            <>
              <strong>It trades objectives against business-as-usual:</strong> fuel cost{' '}
              {pct(d.fuel_cost.delta_pct)}, CO₂e {pct(d.ghg_wtw.delta_pct)}, OPEX {pct(d.opex.delta_pct)}.
            </>
          )}
        </p>
        <div className="verdict__actions">
          <Link className="btn btn--primary" to="/scenarios">
            Compare policy scenarios
            <Icon name="arrowRight" size={15} />
          </Link>
          <Link className="btn" to="/benchmark">
            Check the benchmarks
          </Link>
        </div>
      </div>

      <div className="verdict__aside">
        <ConfidenceGauge predictor={predictor} />
        <QualityGauge baseline={baseline} />
      </div>
    </section>
  )
}

const LEVEL_LABEL = { low: 'Low', medium: 'Medium', high: 'High' }
const LEVEL_ICON = { low: 'xCircle', medium: 'alert', high: 'checkCircle' }

function Gauge({ label, level, note }) {
  return (
    <div className={`gauge${level ? ` gauge--${level}` : ''}`}>
      <div className="gauge__row">
        <span className="gauge__label">{label}</span>
        <span className="gauge__value">
          {level && <Icon name={LEVEL_ICON[level]} size={15} />}
          {level ? LEVEL_LABEL[level] : 'Unknown'}
        </span>
      </div>
      <div className="gauge__track" aria-hidden="true">
        <span className="gauge__seg" />
        <span className="gauge__seg" />
        <span className="gauge__seg" />
      </div>
      <span className="gauge__note">{note}</span>
    </div>
  )
}

/** Confidence in the fuel surrogate, read off its held-out test error. */
function ConfidenceGauge({ predictor }) {
  const mape = predictor?.metrics?.test_mape
  if (mape == null) return <Gauge label="Prediction confidence" note="No test metrics reported by the surrogate." />
  // ponytail: fixed MAPE bands (10% / 25%); make them config-driven if the thresholds get debated.
  const level = mape <= 10 ? 'high' : mape <= 25 ? 'medium' : 'low'
  const r2 = predictor.metrics.test_r2
  return (
    <Gauge
      label="Prediction confidence"
      level={level}
      note={
        <>
          Surrogate test MAPE <span className="mono">{num(mape, 1)}%</span>
          {r2 != null && (
            <>
              {' '}
              · R² <span className="mono">{num(r2, 2)}</span>
            </>
          )}
        </>
      }
    />
  )
}

/** Quality of the search result, read off the size of the Pareto archive. */
function QualityGauge({ baseline }) {
  const n = baseline.pareto_size
  // ponytail: archive-size bands (1 / <10 / ≥10); swap for hypervolume once the overview exposes it.
  const level = n >= 10 ? 'high' : n > 1 ? 'medium' : 'low'
  return (
    <Gauge
      label="Search quality"
      level={level}
      note={
        n === 1 ? (
          'A single non-dominated solution — no trade-off front to choose from.'
        ) : (
          <>
            <span className="mono">{num(n)}</span> non-dominated solutions on the front.
          </>
        )
      }
    />
  )
}
