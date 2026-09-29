import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { BarChart, GroupedColumnChart } from '../components/charts/BarChart'
import { Figure } from '../components/charts/Figure'
import { LineChart } from '../components/charts/LineChart'
import { ScatterChart } from '../components/charts/ScatterChart'
import { DataTable } from '../components/DataTable'
import { Pill, SelectField } from '../components/Field'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { Disclosure, Panel } from '../components/Panel'
import { PlanTable } from '../components/PlanTable'
import { StatTile } from '../components/StatTile'
import { EmptyState, ErrorState, Loader } from '../components/States'
import { useResource } from '../hooks/useResource'
import { compact, fuelLabel, num, seconds, usd } from '../lib/format'
import { feasibilityInsight, hypervolumeInsight, mixInsight, paretoInsight } from '../lib/insights'
import { FUEL_ORDER, SERIES, fuelColor } from '../lib/palette'

export default function Scenarios() {
  const list = useResource(() => api.scenarios(), [])
  const [selected, setSelected] = useState('')
  const scenarios = list.data?.scenarios || []
  const active = selected || scenarios[0]?.name || ''

  const detail = useResource(() => api.scenario(active), [active], { enabled: Boolean(active) })
  const sweep = useResource(() => api.carbonSweep(), [])

  if (list.loading) {
    return (
      <>
        <PageHeader title="Policy scenarios" />
        <div className="content">
          <Loader label="Loading pre-computed scenarios…" />
        </div>
      </>
    )
  }

  if (list.error && !list.data) {
    return (
      <>
        <PageHeader title="Policy scenarios" />
        <div className="content">
          <ErrorState error={list.error} onRetry={list.reload} />
        </div>
      </>
    )
  }

  if (!scenarios.length) {
    return (
      <>
        <PageHeader title="Policy scenarios" />
        <div className="content">
          <Panel>
            <EmptyState icon="compass" title="No scenarios have been pre-computed">
              Run <code className="mono">make optimize</code> to populate{' '}
              <code className="mono">outputs/case_study/</code>.
            </EmptyState>
          </Panel>
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Policy scenarios"
        subtitle="How carbon pricing, CII tightening and fuel subsidies reshape the recommended deployment"
        actions={<Pill>{scenarios.length} pre-computed</Pill>}
      />

      <div className="content">
        <div className="filterbar">
          <SelectField
            label="Scenario"
            value={active}
            onChange={setSelected}
            options={scenarios.map((s) => ({ value: s.name, label: s.label }))}
            hint="Sets the scenario for section 2 below. The comparison charts in section 1 always show all four."
          />
        </div>

        <ScenarioComparison scenarios={scenarios} />

        {detail.loading && !detail.data && <Loader label="Loading scenario artifacts…" />}
        {detail.error && !detail.data && <ErrorState error={detail.error} onRetry={detail.reload} />}
        {detail.data && <ScenarioDetail detail={detail.data} refetching={detail.refetching} />}

        <CarbonSweep sweep={sweep} />
      </div>
    </>
  )
}

/** Cross-scenario comparison of the knee solution's three objectives. */
function ScenarioComparison({ scenarios }) {
  const withKpis = scenarios.filter((s) => s.knee_kpis)
  if (withKpis.length < 2) return null

  const groups = withKpis.map((s) => ({ key: s.name, label: s.label.replace(/\s*\(.*\)$/, '') }))

  // Three objectives on three separate axes — never one plot with two scales.
  const charts = [
    { key: 'fuel_cost_usd', label: 'Fuel cost', format: (v) => compact(v), color: SERIES[0], unit: 'USD' },
    { key: 'ghg_wtw_tco2e', label: 'Well-to-wake CO₂e', format: (v) => compact(v), color: SERIES[0], unit: 't' },
    { key: 'opex_usd', label: 'Total OPEX', format: (v) => compact(v), color: SERIES[0], unit: 'USD' },
  ]

  return (
    <section className="section">
      <div className="section-head">
        <h2 className="section-head__title">1 · All four scenarios compared</h2>
        <span className="section-head__note">
          One bar per policy. Each chart is a single measure, so the three never share an axis.
        </span>
      </div>
      <div className="grid grid--3">
        {charts.map((c) => {
          const best = withKpis.reduce((a, b) => (b.knee_kpis[c.key] < a.knee_kpis[c.key] ? b : a))
          return (
        <Figure
          key={c.key}
          title={c.label}
          subtitle={`Recommended plan per scenario (${c.unit})`}
          chart={
            <GroupedColumnChart
              groups={groups}
              series={[
                {
                  key: c.key,
                  label: c.label,
                  color: c.color,
                  values: Object.fromEntries(withKpis.map((s) => [s.name, s.knee_kpis[c.key]])),
                },
              ]}
              height={220}
              formatValue={c.format}
              ariaLabel={`${c.label} of the recommended plan in each scenario`}
            />
          }
          tableColumns={[
            { key: 'label', label: 'Scenario' },
            { key: 'value', label: c.label, align: 'right', render: (r) => (c.unit === 'USD' ? usd(r.value) : `${num(r.value)} t`) },
          ]}
            tableRows={withKpis.map((s) => ({ label: s.label, value: s.knee_kpis[c.key] }))}
            tableCaption={`${c.label} of each scenario's recommended plan.`}
            insight={`Lowest under ${best.label}: ${c.unit === 'USD' ? usd(best.knee_kpis[c.key]) : `${compact(best.knee_kpis[c.key])} t`}.`}
          />
          )
        })}
      </div>
    </section>
  )
}

/** Detail for the selected scenario: KPIs, Pareto front, fuel mix, plan. */
function ScenarioDetail({ detail, refetching }) {
  const deltas = detail.deltas
  const mixBars = FUEL_ORDER.filter((f) => detail.fuel_mix_pct[f] != null).map((f) => ({
    key: f,
    label: fuelLabel(f),
    value: detail.fuel_mix_pct[f],
    color: fuelColor(f),
  }))

  const paretoPoints = detail.pareto.map((p) => ({
    id: p.solution_id,
    x: p.fuel_cost_usd,
    y: p.ghg_wtw_tco2e,
    highlight: p.is_knee,
    meta: [{ label: 'OPEX', color: SERIES[3], value: usd(p.opex_usd) }],
  }))

  const history = detail.history
  const hvSeries = history
    ? [
        {
          key: 'hv',
          label: 'Archive hypervolume',
          color: SERIES[0],
          points: history.generation.map((g, i) => ({ x: g, y: history.hypervolume[i] })),
        },
      ]
    : []
  const feasSeries = history
    ? [
        {
          key: 'feasible',
          label: 'Feasible individuals',
          color: SERIES[2],
          points: history.generation.map((g, i) => ({ x: g, y: history.feasible_count[i] })),
        },
      ]
    : []

  return (
    <section className={`section${refetching ? ' is-refetching' : ''}`}>
      <div className="section-head">
        <h2 className="section-head__title">2 · Selected scenario — {detail.label}</h2>
        <span className="section-head__note">
          Everything from here down is this one scenario in detail.
        </span>
      </div>

      <div className="grid grid--kpi">
        <StatTile
          label="Fuel cost"
          value={usd(deltas?.fuel_cost.opt ?? detail.knee.objectives.fuel_cost_usd)}
          delta={deltas?.fuel_cost.delta_pct}
          deltaLabel="vs BAU"
          foot={deltas ? `BAU ${usd(deltas.fuel_cost.bau)}` : undefined}
        />
        <StatTile
          label="Well-to-wake CO₂e"
          value={compact(deltas?.ghg_wtw.opt ?? detail.knee.objectives.ghg_wtw_tco2e)}
          unit="t"
          delta={deltas?.ghg_wtw.delta_pct}
          deltaLabel="vs BAU"
          foot={deltas ? `BAU ${compact(deltas.ghg_wtw.bau)} t` : undefined}
        />
        <StatTile
          label="Total OPEX"
          value={usd(deltas?.opex.opt ?? detail.knee.objectives.opex_usd)}
          delta={deltas?.opex.delta_pct}
          deltaLabel="vs BAU"
          foot={deltas ? `BAU ${usd(deltas.opex.bau)}` : undefined}
        />
        <StatTile
          label="Constraints"
          value={detail.knee.feasible ? 'Feasible' : 'Infeasible'}
          foot={
            detail.summary?.fuel_switches_count != null
              ? `${detail.summary.fuel_switches_count} fuel switches · avg speed ${num(detail.summary.avg_speed_delta_kn, 2)} kn vs BAU`
              : 'Cargo demand, schedules, CII bands and bunkerability'
          }
        />
      </div>

      {detail.pareto.length === 1 && (
        <div className="note">
          <Icon name="info" size={18} className="note__icon" />
          <span>
            <strong>This scenario's archive holds a single non-dominated solution.</strong> There is no
            trade-off curve to explore and the cheapest, recommended and greenest picks all collapse onto
            the same plan — QIEA converged to one point rather than spreading a front. The benchmark page
            shows the same effect in the archive-size column.
          </span>
        </div>
      )}

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
              ariaLabel="Pareto solutions plotted by fuel cost and lifecycle emissions"
            />
          }
          tableColumns={[
            { key: 'solution_id', label: 'Solution' },
            { key: 'fuel_cost_usd', label: 'Fuel cost', align: 'right', render: (r) => usd(r.fuel_cost_usd) },
            { key: 'ghg_wtw_tco2e', label: 'CO₂e (t)', align: 'right', render: (r) => num(r.ghg_wtw_tco2e) },
            { key: 'opex_usd', label: 'OPEX', align: 'right', render: (r) => usd(r.opex_usd) },
            { key: 'is_knee', label: 'Recommended', render: (r) => (r.is_knee ? '★' : '') },
          ]}
          tableRows={detail.pareto}
          tableCaption="Every non-dominated solution in this scenario's archive."
          insight={paretoInsight(detail.pareto)}
        />

        <Figure
          title="Fuel mix of the recommended plan"
          subtitle="Share of deployed vessels bunkering each fuel"
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
            { key: 'value', label: 'Share', align: 'right', render: (r) => `${num(r.value, 1)}%` },
          ]}
          tableRows={mixBars}
          tableCaption="Fuel mix of the recommended plan."
          insight={mixInsight(mixBars)}
        />
      </div>

      {history && (
        <div className="grid grid--2">
          <Figure
            title="Search convergence — archive quality"
            subtitle={`Hypervolume of the non-dominated archive across ${history.generation.length} generations`}
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
            insight={hypervolumeInsight(history)}
          />
          <Figure
            title="Search convergence — feasibility"
            subtitle="Individuals satisfying every hard constraint after repair, per generation"
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
            insight={feasibilityInsight(history)}
          />
        </div>
      )}

      {detail.pareto.length > 1 && (
        <Panel
          title="Three ways to deploy"
          subtitle="The cheapest, the balanced recommendation, and the lowest-emission plan"
          flush
        >
          <DataTable
            columns={[
              { key: 'tier', label: 'Option', render: (r) => <strong>{r.tier}</strong> },
              { key: 'solution_id', label: 'Solution' },
              { key: 'fuel_cost_usd', label: 'Fuel cost', align: 'right', render: (r) => usd(r.fuel_cost_usd) },
              { key: 'ghg_wtw_tco2e', label: 'CO₂e (t)', align: 'right', render: (r) => num(r.ghg_wtw_tco2e) },
              { key: 'opex_usd', label: 'OPEX', align: 'right', render: (r) => usd(r.opex_usd) },
              {
                key: 'extra_cost_vs_cheapest',
                label: 'Premium vs cheapest',
                align: 'right',
                render: (r) => (r.extra_cost_vs_cheapest > 0 ? `+${usd(r.extra_cost_vs_cheapest)}` : '—'),
              },
              { key: 'best_for', label: 'Best for' },
            ]}
            rows={detail.three_options}
            rowKey={(r) => r.tier}
            highlight={(r) => r.tier === 'Recommended'}
          />
        </Panel>
      )}

      <Disclosure
        title="Deployment plan"
        subtitle={`${detail.plan.filter((p) => p.assigned).length} of ${detail.plan.length} vessels deployed${
          detail.elapsed_seconds ? ` · solved in ${seconds(detail.elapsed_seconds)}` : ''
        }`}
        count={`${detail.plan.length} vessels`}
      >
        <PlanTable
          plan={detail.plan}
          caption="Rows that differ from business-as-usual are highlighted."
        />
      </Disclosure>
    </section>
  )
}

/** Carbon price sensitivity: fuel shares against the carbon price. */
function CarbonSweep({ sweep }) {
  const series = useMemo(() => {
    const rows = sweep.data?.rows || []
    if (!rows.length) return []
    const defs = [
      { key: 'hfo_pct', fuel: 'HFO' },
      { key: 'lng_pct', fuel: 'LNG_DIESEL' },
      { key: 'meoh_pct', fuel: 'MEOH_GREEN' },
    ]
    return defs
      .filter((d) => rows.some((r) => r[d.key] != null))
      .map((d) => ({
        key: d.key,
        label: fuelLabel(d.fuel),
        color: fuelColor(d.fuel),
        points: rows.map((r) => ({ x: r.carbon_price, y: r[d.key] })),
      }))
  }, [sweep.data])

  const sweepInsight = useMemo(() => {
    const rows = sweep.data?.rows || []
    if (rows.length < 2) return null
    const first = rows[0]
    const last = rows[rows.length - 1]
    return `From $${num(first.carbon_price)} to $${num(last.carbon_price)}/t, HFO moves from ${num(first.hfo_pct, 0)}% to ${num(last.hfo_pct, 0)}% of the fleet and green methanol from ${num(first.meoh_pct, 0)}% to ${num(last.meoh_pct, 0)}%.`
  }, [sweep.data])

  if (sweep.loading) return <Loader label="Loading the carbon sweep…" />
  if (!sweep.data?.available) {
    return (
      <Panel title="Carbon price sensitivity">
        <EmptyState icon="activity" title="No sweep on disk">
          Generate <code className="mono">outputs/case_study/carbon_sweep.csv</code> with{' '}
          <code className="mono">make optimize</code>.
        </EmptyState>
      </Panel>
    )
  }

  return (
    <Figure
      title="Carbon price sensitivity"
      subtitle="Share of the fleet on each fuel as the carbon price rises — where the lines cross, the cheapest fuel changes"
      refetching={sweep.refetching}
      chart={
        <LineChart
          series={series}
          height={280}
          xLabel="Carbon price ($/t-CO₂e)"
          yLabel="Share of fleet (%)"
          formatX={(v) => `$${num(v)}`}
          formatY={(v) => `${num(v)}%`}
          formatValue={(v) => `${num(v, 1)}%`}
          zeroBase
          ariaLabel="Fleet fuel shares against carbon price"
        />
      }
      tableColumns={[
        { key: 'carbon_price', label: 'Carbon price ($/t)', align: 'right', render: (r) => `$${num(r.carbon_price)}` },
        { key: 'hfo_pct', label: 'HFO', align: 'right', render: (r) => `${num(r.hfo_pct, 1)}%` },
        { key: 'lng_pct', label: 'LNG (Diesel)', align: 'right', render: (r) => `${num(r.lng_pct, 1)}%` },
        { key: 'meoh_pct', label: 'Methanol (green)', align: 'right', render: (r) => `${num(r.meoh_pct, 1)}%` },
      ]}
      tableRows={sweep.data.rows}
      tableCaption="Fleet fuel shares at each swept carbon price."
      insight={sweepInsight}
    />
  )
}
