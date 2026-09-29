import { useMemo, useRef, useState } from 'react'
import { IS_STATIC, api } from '../api/client'
import { BarChart } from '../components/charts/BarChart'
import { Figure } from '../components/charts/Figure'
import { DataTable } from '../components/DataTable'
import { NumberField, Pill, SelectField, SliderField } from '../components/Field'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { Disclosure, Panel } from '../components/Panel'
import { StatTile } from '../components/StatTile'
import { ErrorState, Loader } from '../components/States'
import { useResource } from '../hooks/useResource'
import { compact, fuelLabel, num, titleCase, weatherLabel } from '../lib/format'
import { SERIES, shipColor } from '../lib/palette'

const VESSEL_COLUMNS = [
  { key: 'id', label: 'Vessel' },
  { key: 'type', label: 'Type', render: (v) => titleCase(v.type) },
  { key: 'dwt', label: 'DWT', align: 'right', render: (v) => num(v.dwt) },
  { key: 'capacity_teu', label: 'Capacity', align: 'right', render: (v) => num(v.capacity_teu) },
  { key: 'engine_kw', label: 'Engine kW', align: 'right', render: (v) => num(v.engine_kw) },
  { key: 'design_speed', label: 'Design kn', align: 'right', render: (v) => num(v.design_speed, 1) },
  {
    key: 'speed_band',
    label: 'Speed band',
    align: 'right',
    render: (v) => `${num(v.vmin, 1)}–${num(v.vmax, 1)} kn`,
  },
  {
    key: 'fuel_per_nm_kg',
    label: 'kg/nm',
    align: 'right',
    render: (v) => num(v.fuel_per_nm_kg, 1),
  },
  {
    key: 'fuels_allowed',
    label: 'Bunkerable fuels',
    render: (v) => (v.fuels_allowed || []).map(fuelLabel).join(', '),
  },
  {
    key: 'charter_per_day',
    label: 'Charter $/day',
    align: 'right',
    render: (v) => num(v.charter_per_day),
  },
]

const ROUTE_COLUMNS = [
  { key: 'id', label: 'Route' },
  { key: 'distance_nm', label: 'Distance nm', align: 'right', render: (r) => num(r.distance_nm) },
  { key: 'demand_teu', label: 'Demand', align: 'right', render: (r) => num(r.demand_teu) },
  { key: 'schedule_days', label: 'Schedule days', align: 'right', render: (r) => num(r.schedule_days, 1) },
  {
    key: 'required_speed',
    label: 'Required kn',
    align: 'right',
    render: (r) => num(r.distance_nm / Math.max(1, r.schedule_days * 24), 1),
  },
  { key: 'weather_severity', label: 'Sea state', render: (r) => weatherLabel(r.weather_severity) },
  {
    key: 'availability',
    label: 'Bunkering & shore power',
    render: (r) => (
      <span className="btn-row" style={{ gap: 4, flexWrap: 'nowrap' }}>
        {r.lng_available && <span className="tag">LNG</span>}
        {r.meoh_available && <span className="tag">Methanol</span>}
        {r.shore_power && <span className="tag">Shore power</span>}
        {!r.lng_available && !r.meoh_available && !r.shore_power && <span className="muted">HFO only</span>}
      </span>
    ),
  },
]

export default function Fleet({ onFleetChange }) {
  const fleet = useResource(() => api.fleet(), [])
  const files = useResource(() => api.fleetFiles(), [])
  const [busy, setBusy] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [gen, setGen] = useState({ vessels: 20, routes: 5, seed: 42 })
  const [selectedFile, setSelectedFile] = useState('')
  const fileInput = useRef(null)

  const runAction = async (label, fn) => {
    setBusy(label)
    setActionError(null)
    try {
      await fn()
      await fleet.reload()
      await files.reload()
      onFleetChange?.()
    } catch (err) {
      setActionError(err)
    } finally {
      setBusy(null)
    }
  }

  const fileOptions = (files.data?.files || []).map((f) => ({
    value: f.name,
    label: `${f.name} — ${f.vessels} ships, ${f.routes} routes`,
  }))
  const activeFile = selectedFile || fleet.data?.source || fileOptions[0]?.value || ''

  // Summaries derived from the same /fleet payload the tables render.
  const demandBars = useMemo(
    () =>
      (fleet.data?.routes || []).map((r) => ({
        key: r.id,
        label: r.id,
        value: r.demand_teu,
        color: SERIES[0],
      })),
    [fleet.data],
  )
  const typeBars = useMemo(() => {
    const counts = {}
    ;(fleet.data?.vessels || []).forEach((v) => {
      counts[v.type] = (counts[v.type] || 0) + 1
    })
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([type, n]) => ({ key: type, label: titleCase(type), value: n, color: shipColor(type) }))
  }, [fleet.data])
  const totalDemand = demandBars.reduce((a, b) => a + b.value, 0)
  const biggestRoute = [...demandBars].sort((a, b) => b.value - a.value)[0]

  return (
    <>
      <PageHeader
        title="Fleet & commercial routes"
        subtitle="The vessel catalogue and route corridors every optimisation run is solved against"
        actions={fleet.data && <Pill tone="good">{fleet.data.source}</Pill>}
      />

      <div className="content">
        {fleet.loading && <Loader label="Loading the active fleet…" />}
        {fleet.error && !fleet.data && <ErrorState error={fleet.error} onRetry={fleet.reload} />}

        {fleet.data && (
          <>
            <div className="grid grid--kpi">
              <StatTile label="Vessels" value={num(fleet.data.totals.vessels)} unit="ships" />
              <StatTile
                label="Route corridors"
                value={num(fleet.data.totals.routes)}
                foot={`${compact(fleet.data.totals.distance_nm)} nm of round trips`}
              />
              <StatTile
                label="Fleet capacity"
                value={compact(fleet.data.totals.capacity_teu)}
                unit="TEU-equiv"
                foot={`${compact(fleet.data.totals.dwt)} t deadweight`}
              />
              <StatTile
                label="Cargo demand"
                value={compact(fleet.data.totals.demand_teu)}
                unit="TEU"
                foot="Must be met in full by every feasible plan"
              />
            </div>

            {IS_STATIC && (
              <div className="note">
                <Icon name="info" size={18} className="note__icon" />
                <span>
                  <strong>Read-only snapshot.</strong> This published demo carries the 20-vessel,
                  5-route case-study fleet. Loading, uploading and synthesising a fleet all run
                  Python on the backend, so those controls are disabled here — start it with{' '}
                  <code className="mono">make api</code> to manage fleets for real.
                </span>
              </div>
            )}

            <div className="grid grid--2">
              <Figure
                title="Cargo demand by route"
                subtitle="TEU each corridor must move in full — the hard constraint every plan is solved against"
                chart={
                  <BarChart
                    bars={demandBars}
                    formatValue={(v) => compact(v)}
                    formatLabel={(v) => num(v)}
                    ariaLabel="Cargo demand in TEU per route"
                  />
                }
                tableColumns={[
                  { key: 'label', label: 'Route' },
                  { key: 'value', label: 'Demand (TEU)', align: 'right', render: (r) => num(r.value) },
                ]}
                tableRows={demandBars}
                insight={
                  biggestRoute &&
                  totalDemand > 0 &&
                  `${biggestRoute.label} alone carries ${num((biggestRoute.value / totalDemand) * 100, 0)}% of total demand, so its assignment dominates every plan.`
                }
              />
              <Figure
                title="Vessel mix"
                subtitle="Ships per classification in the active fleet"
                chart={
                  <BarChart
                    bars={typeBars}
                    formatValue={(v) => num(v)}
                    ariaLabel="Number of vessels per ship type"
                  />
                }
                tableColumns={[
                  { key: 'label', label: 'Type' },
                  { key: 'value', label: 'Vessels', align: 'right' },
                ]}
                tableRows={typeBars}
                insight={
                  typeBars[0] &&
                  `${typeBars[0].label} is the largest class at ${typeBars[0].value} of ${fleet.data.vessels.length} ships.`
                }
              />
            </div>

            <div className="grid grid--2">
              <Panel
                title="Load a fleet"
                subtitle="Activate a committed fleet file or upload your own specification"
              >
                <div className="stack">
                  <SelectField
                    label="Fleet file in data/synthetic"
                    value={activeFile}
                    onChange={setSelectedFile}
                    options={fileOptions.length ? fileOptions : [{ value: '', label: 'No files found' }]}
                  />
                  <div className="btn-row">
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled={IS_STATIC || !activeFile || busy != null}
                      onClick={() => runAction('load', () => api.loadFleet(activeFile))}
                    >
                      {busy === 'load' ? 'Loading…' : 'Activate fleet'}
                    </button>
                    <button
                      type="button"
                      className="btn"
                      disabled={IS_STATIC || busy != null}
                      onClick={() => fileInput.current?.click()}
                    >
                      Upload JSON…
                    </button>
                    <input
                      ref={fileInput}
                      type="file"
                      accept="application/json,.json"
                      hidden
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) runAction('upload', () => api.uploadFleetFile(file))
                        e.target.value = ''
                      }}
                    />
                  </div>
                  <div className="field__hint">
                    An uploaded file needs a non-empty <code className="mono">vessels</code> and{' '}
                    <code className="mono">routes</code> array; optional fields are back-filled.
                  </div>
                </div>
              </Panel>

              <Panel
                title="Synthesise a calibrated fleet"
                subtitle="Naval parameters drawn from verified EU MRV THETIS distributions"
              >
                <div className="stack">
                  <SliderField
                    label="Fleet size"
                    value={gen.vessels}
                    display={`${gen.vessels} ships`}
                    min={5}
                    max={200}
                    step={5}
                    onChange={(v) => setGen((g) => ({ ...g, vessels: v }))}
                  />
                  <SliderField
                    label="Route corridors"
                    value={gen.routes}
                    display={`${gen.routes} routes`}
                    min={2}
                    max={20}
                    onChange={(v) => setGen((g) => ({ ...g, routes: v }))}
                  />
                  <NumberField
                    label="Random seed"
                    value={gen.seed}
                    min={0}
                    max={9999}
                    onChange={(v) => setGen((g) => ({ ...g, seed: v }))}
                    hint="Same seed, same fleet — every run stays reproducible."
                  />
                  <div className="btn-row">
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled={IS_STATIC || busy != null}
                      onClick={() => runAction('generate', () => api.generateFleet(gen))}
                    >
                      {busy === 'generate' ? 'Synthesising…' : 'Synthesise & activate'}
                    </button>
                  </div>
                  <div className="field__hint">
                    Writes <code className="mono">data/synthetic/fleet_{gen.vessels}v_{gen.routes}r_seed
                    {gen.seed}.json</code> and makes it the active fleet.
                  </div>
                </div>
              </Panel>
            </div>

            {actionError && (
              <Panel>
                <ErrorState error={actionError} title="That fleet action failed" />
              </Panel>
            )}

            <Disclosure
              title="Vessel catalogue"
              subtitle="bunkerable fuels differ per ship; the optimiser may only pick from each vessel's own list"
              count={`${fleet.data.vessels.length} vessels`}
            >
              <div className={fleet.refetching ? 'is-refetching' : undefined}>
                <DataTable columns={VESSEL_COLUMNS} rows={fleet.data.vessels} rowKey={(v) => v.id} tall />
              </div>
            </Disclosure>

            <Disclosure
              title="Route corridors"
              subtitle="required speed is distance ÷ schedule; routes at or above a vessel's vmax cannot be served on time"
              count={`${fleet.data.routes.length} routes`}
            >
              <div className={fleet.refetching ? 'is-refetching' : undefined}>
                <DataTable columns={ROUTE_COLUMNS} rows={fleet.data.routes} rowKey={(r) => r.id} />
              </div>
            </Disclosure>
          </>
        )}
      </div>
    </>
  )
}
