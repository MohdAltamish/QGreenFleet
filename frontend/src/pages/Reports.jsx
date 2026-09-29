import { useState } from 'react'
import { IS_STATIC, api, chartUrl, reportUrl } from '../api/client'
import { DataTable } from '../components/DataTable'
import { Pill, SelectField } from '../components/Field'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { Panel } from '../components/Panel'
import { EmptyState, ErrorState, Loader } from '../components/States'
import { useResource } from '../hooks/useResource'
import { bytes, num, titleCase } from '../lib/format'

const FIGURE_CAPTIONS = {
  'architecture_diagram.png': 'End-to-end system architecture.',
  'carbon_sweep.png': 'Fuel shares against the carbon price.',
  'data_trust_diagram.png': 'Data provenance and calibration chain.',
  'fleet_map.png': 'Commercial corridors and port infrastructure.',
  'fuel_mix_donut.png': 'Fuel mix of the recommended plan.',
  'ghg_waterfall.png': 'Emission reduction decomposed by lever.',
  'kpi_bars.png': 'Headline KPIs against business-as-usual.',
  'pareto_scatter.png': 'Pareto trade-off surface.',
  'speed_dumbbell.png': 'Per-vessel speed change against BAU.',
  'speed_fuel_curve.png': 'Speed–fuel admiralty curves.',
  'waterfall_simple.png': 'Simplified emission waterfall.',
}

export default function Reports() {
  const reports = useResource(() => api.reports(), [])
  const charts = useResource(() => api.charts(), [])
  const factors = useResource(() => api.emissionsFactors(), [])
  const [gallery, setGallery] = useState('charts')

  const figures = (gallery === 'charts' ? charts.data?.charts : charts.data?.outputs) || []

  return (
    <>
      <PageHeader
        title="Reports & figure library"
        subtitle="Publication-ready PDFs, the rendered figure library, and the emission factor reference"
      />

      <div className="content">
        <Panel
          title="Document exports"
          subtitle="Pre-compiled from the committed case study — an executive read and a full technical report"
        >
          {reports.loading && <Loader />}
          {reports.error && !reports.data && <ErrorState error={reports.error} onRetry={reports.reload} />}
          {reports.data && (
            <div className="grid grid--2">
              {reports.data.reports.map((r) => (
                <div key={r.key} className="doc">
                  <div className="row-between">
                    <div className="doc__name">{r.label}</div>
                    <Pill tone={r.available ? 'good' : 'critical'}>
                      {r.available ? bytes(r.size_bytes) : 'not generated'}
                    </Pill>
                  </div>
                  <div className="mono muted">{r.filename}</div>
                  <div className="btn-row">
                    {r.available ? (
                      <a className="btn btn--primary" href={reportUrl(r.key)} download>
                        <Icon name="download" size={15} />
                        Download PDF
                      </a>
                    ) : (
                      <button type="button" className="btn" disabled>
                        Download PDF
                      </button>
                    )}
                    {r.available && (
                      <a className="btn" href={reportUrl(r.key)} target="_blank" rel="noreferrer">
                        Open in a tab
                      </a>
                    )}
                  </div>
                  {!r.available && (
                    <div className="field__hint">
                      {IS_STATIC
                        ? 'Both PDFs are committed under docs/samples/. Serving a file download needs the FastAPI backend, so it is disabled in this published snapshot.'
                        : 'Generate it with `make optimize`.'}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Figure library"
          subtitle={
            IS_STATIC
              ? 'PNGs rendered by the analysis pipeline, embedded in this snapshot'
              : 'PNGs rendered by the analysis pipeline, served straight from the backend'
          }
          actions={
            <SelectField
              label=""
              value={gallery}
              onChange={setGallery}
              options={
                IS_STATIC
                  ? [{ value: 'charts', label: `charts/ (${charts.data?.charts?.length ?? 0})` }]
                  : [
                      { value: 'charts', label: `charts/ (${charts.data?.charts?.length ?? 0})` },
                      { value: 'outputs', label: `outputs/ (${charts.data?.outputs?.length ?? 0})` },
                    ]
              }
            />
          }
        >
          {charts.loading && <Loader />}
          {charts.error && !charts.data && <ErrorState error={charts.error} onRetry={charts.reload} />}
          {charts.data && figures.length === 0 && (
            <EmptyState icon="image" title="No figures in this directory">
              Run the pipeline to render them.
            </EmptyState>
          )}
          {figures.length > 0 && (
            <div className="grid grid--3">
              {figures.map((name) => (
                <figure key={name} style={{ margin: 0 }}>
                  <a href={chartUrl(name)} target="_blank" rel="noreferrer">
                    <img
                      src={chartUrl(name)}
                      alt={FIGURE_CAPTIONS[name] || titleCase(name.replace(/\.png$/, ''))}
                      loading="lazy"
                      className="figure-thumb"
                    />
                  </a>
                  <figcaption className="field__hint" style={{ marginTop: 8 }}>
                    {FIGURE_CAPTIONS[name] || <span className="mono">{name}</span>}
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Fuel emission factors"
          subtitle="IMO Fourth GHG Study 2020 and FuelEU Maritime Annex II, at GWP100 (IPCC AR5)"
          flush
        >
          {factors.loading && <Loader />}
          {factors.error && !factors.data && <ErrorState error={factors.error} onRetry={factors.reload} />}
          {factors.data && (
            <DataTable
              columns={[
                {
                  key: 'fuel',
                  label: 'Fuel',
                  render: (r) => (
                    <span>
                      <span className="mono">{r.fuel}</span>{' '}
                      {r.optimizer_selectable && <span className="tag">selectable</span>}
                    </span>
                  ),
                },
                { key: 'lhv_mj_kg', label: 'LHV MJ/kg', align: 'right', render: (r) => num(r.lhv_mj_kg, 1) },
                { key: 'ttw_g_mj', label: 'Tank-to-wake g/MJ', align: 'right', render: (r) => num(r.ttw_g_mj, 1) },
                { key: 'wtt_g_mj', label: 'Well-to-tank g/MJ', align: 'right', render: (r) => num(r.wtt_g_mj, 1) },
                { key: 'wtw_g_mj', label: 'Well-to-wake g/MJ', align: 'right', render: (r) => num(r.wtw_g_mj, 1) },
              ]}
              rows={factors.data.fuels}
              rowKey={(r) => r.fuel}
              highlight={(r) => r.optimizer_selectable}
              caption="Green methanol carries a negative well-to-tank factor: its biogenic carbon offsets tank-to-wake CO₂, netting ≈10 g-CO₂e/MJ well-to-wake."
            />
          )}
        </Panel>
      </div>
    </>
  )
}
