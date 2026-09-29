import { useMemo } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { LineChart } from '../components/charts/LineChart'
import { Icon } from '../components/Icon'
import { Workflow } from '../components/Workflow'
import { useResource } from '../hooks/useResource'
import { useTheme } from '../hooks/useTheme'
import { num, titleCase } from '../lib/format'
import { shipColor } from '../lib/palette'
import { STEPS, resolveSteps } from '../lib/workflow'

const SHIP_TYPES = ['container', 'bulk', 'tanker']

/**
 * The product's front door. Its visual is the real surrogate — the same
 * /predict/curve call the predictor page makes — not an illustration.
 */
export default function Landing({ health }) {
  const { pathname } = useLocation()
  const { theme, cycle } = useTheme()
  const curve = useResource(
    () =>
      api.predictCurve({
        ship_types: SHIP_TYPES,
        speed_min: 8,
        speed_max: 24,
        points: 33,
        draft_m: 10,
        weather_severity: 1,
      }),
    [],
  )

  const series = useMemo(
    () =>
      (curve.data?.series || []).map((s) => ({
        key: s.ship_type,
        label: titleCase(s.ship_type),
        color: shipColor(s.ship_type),
        points: s.points.map((p) => ({ x: p.speed_kn, y: p.fuel_tons_per_day })),
      })),
    [curve.data],
  )

  // Cubic resistance, measured on the live curve: burn at 14 kn vs 18 kn.
  const container = series.find((s) => s.key === 'container')?.points || []
  const at = (kn) => container.reduce((b, p) => (Math.abs(p.x - kn) < Math.abs(b.x - kn) ? p : b), container[0] || {})
  const slow = container.length ? at(14) : null
  const fast = container.length ? at(18) : null
  const saving = slow && fast && fast.y > 0 ? (1 - slow.y / fast.y) * 100 : null

  const h = health?.data
  const steps = resolveSteps(h, pathname, { pending: health?.loading })

  return (
    <div className="landing">
      <header className="landing__nav">
        <Link to="/" className="brand">
          <span className="brand__mark" aria-hidden="true">
            <Icon name="leaf" size={18} strokeWidth={2} />
          </span>
          <span className="brand__text">
            <span className="brand__name">QGreenFleet</span>
          </span>
        </Link>
        <nav className="landing__nav-links" aria-label="Primary">
          <button type="button" className="icon-btn" onClick={cycle} aria-label={`Theme: ${theme} — change`}>
            <Icon name={{ system: 'monitor', light: 'sun', dark: 'moon' }[theme]} />
          </button>
          <Link className="btn btn--ghost btn--sm" to="/benchmark">
            Benchmarks
          </Link>
          <Link className="btn btn--sm" to="/overview">
            Dashboard
          </Link>
        </nav>
      </header>

      <main>
        <section className="hero">
          <div>
            <span className="hero__badge">
              <span className="hero__badge-dot">SIH #26138</span>
              Quantum-inspired fleet optimisation
            </span>
            <h1 className="hero__title">
              Pick the fuel, speed and route for <em>every ship</em> in the fleet.
            </h1>
            <p className="hero__lede">
              QGreenFleet predicts fuel burn with an EU MRV-calibrated surrogate, then searches deployment,
              bunker fuel and cruising speed with QIEA + QPSO against fuel cost, well-to-wake CO₂e and
              OPEX — and tells you plainly how far to trust the answer.
            </p>
            <div className="btn-row">
              <Link className="btn btn--primary btn--lg" to="/overview">
                Open the dashboard
                <Icon name="arrowRight" size={16} />
              </Link>
              <Link className="btn btn--lg" to="/predict">
                Try the fuel predictor
              </Link>
            </div>
            <div className="hero__meta">
              {h?.fleet?.loaded && (
                <span>
                  <Icon name="ship" size={15} />
                  <span className="mono">{h.fleet.vessels}</span> vessels ·{' '}
                  <span className="mono">{h.fleet.routes}</span> routes loaded
                </span>
              )}
              <span>
                <Icon name="target" size={15} />3 objectives, one Pareto front
              </span>
              {h?.predictor?.available && (
                <span>
                  <Icon name="activity" size={15} />
                  {h.predictor.two_stage ? 'Two-stage MRV surrogate' : h.predictor.model_name}
                </span>
              )}
            </div>
          </div>

          <div className="console" aria-label="Live surrogate output">
            <div className="console__bar">
              <span className="console__lights" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
              <span>Speed–fuel curves · 10 m draft · moderate sea</span>
              <span className="mono">/predict/curve</span>
            </div>
            <div className="console__body">
              {series.length ? (
                <LineChart
                  series={series}
                  height={250}
                  xLabel="Speed (knots)"
                  yLabel="Fuel (t/day)"
                  formatX={(v) => num(v, 0)}
                  formatY={(v) => num(v, 0)}
                  formatValue={(v) => `${num(v, 1)} t/day`}
                  zeroBase
                  ariaLabel="Predicted fuel consumption against speed for container, bulk and tanker vessels"
                />
              ) : (
                <div className="states">
                  {curve.loading ? 'Querying the surrogate…' : 'Connect the API to see the live surrogate.'}
                </div>
              )}
              <div className="console__metrics">
                <div className="console__metric">
                  <div className="console__metric-label">Container @ 18 kn</div>
                  <div className="console__metric-value">{fast ? `${num(fast.y, 1)} t` : '—'}</div>
                </div>
                <div className="console__metric">
                  <div className="console__metric-label">Container @ 14 kn</div>
                  <div className="console__metric-value">{slow ? `${num(slow.y, 1)} t` : '—'}</div>
                </div>
                <div className="console__metric">
                  <div className="console__metric-label">Slow-steaming saving</div>
                  <div className="console__metric-value">{saving != null ? `${num(saving, 0)}%` : '—'}</div>
                </div>
              </div>
            </div>
            <div className="pipeline" aria-label="Pipeline stages">
              {STEPS.map((s, i) => (
                <div key={s.key} className="pipeline__stage" style={{ '--i': i }}>
                  <span className="pipeline__bar" aria-hidden="true" />
                  <span className="pipeline__name">{s.stage}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="landing__section" aria-labelledby="pipeline-title">
          <div className="landing__section-head">
            <h2 id="pipeline-title">From fleet data to a defensible decision</h2>
            <p>
              Input → processing → analysis → validation → result. Every step reads its state from the live
              backend, so what you see here is what this deployment can actually do.
            </p>
          </div>
          <Workflow steps={steps} />
        </section>
      </main>

      <footer className="landing__foot">
        QGreenFleet · quantum-inspired QIEA + QPSO on classical hardware · emission factors from the IMO
        Fourth GHG Study 2020 and FuelEU Maritime.
      </footer>
    </div>
  )
}
