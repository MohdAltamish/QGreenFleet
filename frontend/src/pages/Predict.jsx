import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { Figure } from '../components/charts/Figure'
import { LineChart } from '../components/charts/LineChart'
import { DataTable } from '../components/DataTable'
import { Pill, SelectField, SliderField } from '../components/Field'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { Disclosure } from '../components/Panel'
import { StatTile } from '../components/StatTile'
import { ErrorState, Loader } from '../components/States'
import { useResource } from '../hooks/useResource'
import { num, titleCase, weatherLabel } from '../lib/format'
import { shipColor } from '../lib/palette'

const SHIP_TYPES = ['container', 'bulk', 'tanker']
const CURVE_POINTS = 33

export default function Predict() {
  const [shipType, setShipType] = useState('container')
  const [speed, setSpeed] = useState(15)
  const [draft, setDraft] = useState(10)
  const [weather, setWeather] = useState(1)

  const point = useResource(
    () => api.predict({ ship_type: shipType, speed_kn: speed, draft_m: draft, weather_severity: weather }),
    [shipType, speed, draft, weather],
  )
  const curve = useResource(
    () =>
      api.predictCurve({
        ship_types: SHIP_TYPES,
        speed_min: 8,
        speed_max: 24,
        points: CURVE_POINTS,
        draft_m: draft,
        weather_severity: weather,
      }),
    [draft, weather],
  )
  const models = useResource(() => api.models(), [])

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

  // Table twin of the curve: one row per speed, one column per ship type.
  const curveRows = useMemo(() => {
    if (!series.length) return []
    return series[0].points.map((p, i) => {
      const row = { speed_kn: p.x }
      series.forEach((s) => {
        row[s.key] = s.points[i]?.y
      })
      return row
    })
  }, [series])

  // What a 2 kn speed cut is worth for the selected ship, read off the curve.
  const curveInsight = useMemo(() => {
    const pts = series.find((s) => s.key === shipType)?.points || []
    if (pts.length < 2) return null
    const near = (kn) => pts.reduce((b, p) => (Math.abs(p.x - kn) < Math.abs(b.x - kn) ? p : b), pts[0])
    const here = near(speed)
    const slower = near(speed - 2)
    if (slower.x >= here.x || here.y <= 0) return null
    const cut = (1 - slower.y / here.y) * 100
    return `Slowing a ${shipType} ship from ${num(here.x, 1)} to ${num(slower.x, 1)} kn cuts daily burn by ${num(cut, 0)}% — a ${num((2 / here.x) * 100, 0)}% speed cut.`
  }, [series, shipType, speed])

  return (
    <>
      <PageHeader
        title="Fuel consumption predictor"
        subtitle="Two-stage surrogate: an EU MRV macro baseline adjusted by a voyage hydrodynamic model"
        actions={
          point.data && (
            <Pill tone="good">
              {point.data.two_stage ? 'MRV macro + voyage micro' : point.data.model_name}
            </Pill>
          )
        }
      />

      <div className="content">
        {/* One filter row, above everything it scopes */}
        <div className="filterbar">
          <SelectField
            label="Ship classification"
            value={shipType}
            onChange={setShipType}
            options={SHIP_TYPES.map((t) => ({ value: t, label: titleCase(t) }))}
          />
          <SliderField
            label="Speed over ground"
            value={speed}
            display={`${num(speed, 1)} kn`}
            min={8}
            max={24}
            step={0.5}
            onChange={setSpeed}
          />
          <SliderField
            label="Mean operational draft"
            value={draft}
            display={`${num(draft, 1)} m`}
            min={4}
            max={18}
            step={0.5}
            onChange={setDraft}
          />
          <SelectField
            label="Sea state"
            value={String(weather)}
            onChange={(v) => setWeather(Number(v))}
            options={[0, 1, 2].map((v) => ({ value: String(v), label: weatherLabel(v) }))}
          />
        </div>

        {point.error && !point.data && <ErrorState error={point.error} onRetry={point.reload} />}
        {point.loading && !point.data && <Loader label="Running inference…" />}

        {point.data && (
          <div className={`grid grid--kpi${point.refetching ? ' is-refetching' : ''}`}>
            <StatTile
              label="Predicted fuel burn"
              value={num(point.data.fuel_tons_per_day, 2)}
              unit="t/day"
              hero
              foot={`${titleCase(shipType)} at ${num(speed, 1)} kn`}
            />
            <StatTile
              label="Hourly consumption"
              value={num(point.data.fuel_kg_per_hour, 0)}
              unit="kg/h"
            />
            <StatTile
              label="Distance intensity"
              value={num(point.data.fuel_kg_per_nm, 1)}
              unit="kg/nm"
              foot="The quantity the MRV stage predicts directly"
            />
            <StatTile
              label="Draft & weather factor"
              value={`${num(point.data.hydrodynamic_adjustment, 3)}×`}
              foot="Rule-based multiplier, clipped to 0.70–1.30"
            />
          </div>
        )}

        {point.data && (
          <div className="note">
            <Icon name="info" size={18} className="note__icon" />
            <span>
              <strong>What is learned and what is physics.</strong> The fuel level for each ship class
              comes from a QPSO-tuned XGBoost model trained on EU MRV ship reports. How consumption
              changes with speed follows the admiralty law (fuel per day ∝ speed³, with a part-load
              penalty below the class&apos;s median speed). Draft and sea state apply rule-based factors —
              the {num(point.data.hydrodynamic_adjustment, 3)}× shown above — because the voyage-level
              dataset showed no learnable relation between those conditions and fuel.
            </span>
          </div>
        )}

        <Figure
          title="Speed–fuel admiralty curves"
          subtitle={`Consumption against speed at ${num(draft, 1)} m draft, ${weatherLabel(weather).toLowerCase()} — cubic resistance means small speed cuts pay off disproportionately`}
          refetching={curve.refetching}
          chart={
            curve.loading && !curve.data ? (
              <Loader label="Sweeping speeds…" />
            ) : curve.error && !curve.data ? (
              <ErrorState error={curve.error} onRetry={curve.reload} />
            ) : (
              <LineChart
                series={series}
                height={300}
                xLabel="Speed (knots)"
                yLabel="Fuel (t/day)"
                formatX={(v) => num(v, 1)}
                formatY={(v) => num(v, 0)}
                formatValue={(v) => `${num(v, 1)} t/day`}
                zeroBase
                ariaLabel="Fuel consumption in tons per day against speed, per ship type"
              />
            )
          }
          tableColumns={[
            { key: 'speed_kn', label: 'Speed (kn)', align: 'right', render: (r) => num(r.speed_kn, 1) },
            ...SHIP_TYPES.map((t) => ({
              key: t,
              label: `${titleCase(t)} (t/day)`,
              align: 'right',
              render: (r) => num(r[t], 2),
            })),
          ]}
          tableRows={curveRows}
          tableCaption="Predicted fuel consumption at each swept speed, by ship classification."
          insight={curveInsight}
        />

        <Disclosure
          title="Surrogate model registry"
          subtitle="model selection is config-driven and seeded; metrics come from the trained metadata on disk"
          count={models.data?.registry ? `${models.data.registry.length} candidates` : undefined}
        >
          {models.loading && !models.data ? (
            <Loader />
          ) : models.error && !models.data ? (
            <ErrorState error={models.error} onRetry={models.reload} />
          ) : (
            <DataTable
              columns={[
                {
                  key: 'model',
                  label: 'Model candidate',
                  render: (r) => (
                    <span>
                      {r.model} {r.selected && <span className="tag">★ selected</span>}
                    </span>
                  ),
                },
                { key: 'stage', label: 'Stage' },
                { key: 'cv_rmse', label: '5-fold CV RMSE', align: 'right' },
                { key: 'test_rmse', label: 'Test RMSE', align: 'right' },
                { key: 'test_mape', label: 'Test MAPE', align: 'right' },
              ]}
              rows={models.data.registry}
              rowKey={(r) => r.model}
              highlight={(r) => r.selected}
              emptyLabel="No trained model metadata found. Run `make train` first."
            />
          )}
        </Disclosure>
      </div>
    </>
  )
}
