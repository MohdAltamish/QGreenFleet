import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { GroupedColumnChart } from '../components/charts/BarChart'
import { Figure } from '../components/charts/Figure'
import { DataTable } from '../components/DataTable'
import { Pill, SelectField } from '../components/Field'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { Disclosure, Panel } from '../components/Panel'
import { StatTile } from '../components/StatTile'
import { EmptyState, ErrorState, Loader } from '../components/States'
import { useResource } from '../hooks/useResource'
import { num } from '../lib/format'
import { algoColor } from '../lib/palette'

const INSTANCE_LABELS = {
  S: 'S · 5 ships',
  M: 'M · 20 ships',
  L: 'L · 50 ships',
  XL: 'XL · 100 ships',
}

export default function Benchmark() {
  const bench = useResource(() => api.benchmark(), [])
  const [instance, setInstance] = useState('all')

  const data = bench.data
  const rows = data?.rows || []
  const byInstance = data?.by_instance || []

  const visibleInstances = useMemo(
    () => (instance === 'all' ? data?.instances || [] : [instance]),
    [instance, data],
  )

  const groups = visibleInstances.map((i) => ({ key: i, label: INSTANCE_LABELS[i] || i }))
  // QIEA is the subject of the comparison, so it leads the legend; colors are
  // pinned per algorithm, so reordering never repaints a series.
  const ALGO_ORDER = ['QIEA', 'GA', 'MOPSO', 'SA']
  const algorithms = [...(data?.algorithms || [])].sort(
    (a, b) => ALGO_ORDER.indexOf(a) - ALGO_ORDER.indexOf(b),
  )

  const series = algorithms.map((algo) => ({
    key: algo,
    label: algo,
    color: algoColor(algo),
    values: Object.fromEntries(
      byInstance.filter((r) => r.algo === algo).map((r) => [r.instance, r.hv]),
    ),
  }))
  const timeSeries = algorithms.map((algo) => ({
    key: algo,
    label: algo,
    color: algoColor(algo),
    values: Object.fromEntries(
      byInstance.filter((r) => r.algo === algo).map((r) => [r.instance, r.wall_time_s]),
    ),
  }))
  const archiveSeries = algorithms.map((algo) => ({
    key: algo,
    label: algo,
    color: algoColor(algo),
    values: Object.fromEntries(
      byInstance.filter((r) => r.algo === algo).map((r) => [r.instance, r.archive_size]),
    ),
  }))

  const headline = useMemo(() => {
    const byInstance = data?.by_instance || []
    if (!byInstance.length) return null
    const qieaTime = byInstance.filter((r) => r.algo === 'QIEA').map((r) => r.wall_time_s)
    const gaTime = byInstance.filter((r) => r.algo === 'GA').map((r) => r.wall_time_s)
    const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)
    const qMean = mean(qieaTime)
    const gMean = mean(gaTime)
    const bestHvByInstance = {}
    byInstance.forEach((r) => {
      if (!bestHvByInstance[r.instance] || r.hv > bestHvByInstance[r.instance].hv) {
        bestHvByInstance[r.instance] = r
      }
    })
    const qieaHvWins = Object.values(bestHvByInstance).filter((r) => r.algo === 'QIEA').length
    return {
      speedup: qMean && gMean ? gMean / qMean : null,
      qieaHvWins,
      instanceCount: Object.keys(bestHvByInstance).length,
      bestHvByInstance,
    }
  }, [data])

  return (
    <>
      <PageHeader
        title="Algorithm benchmarks"
        subtitle="QIEA+QPSO against NSGA-II, MOPSO and simulated annealing across four instance sizes"
        actions={data?.seeds?.length ? <Pill>{data.seeds.length} seeds per cell</Pill> : null}
      />

      <div className="content">
        {bench.loading && <Loader label="Loading benchmark results…" />}
        {bench.error && !data && <ErrorState error={bench.error} onRetry={bench.reload} />}

        {data && !data.available && (
          <Panel>
            <EmptyState icon="bars" title="No benchmark results on disk">
              Run <code className="mono">make benchmark</code> to produce{' '}
              <code className="mono">outputs/benchmark_results.csv</code>.
            </EmptyState>
          </Panel>
        )}

        {data?.available && (
          <>
            <div className="grid grid--kpi">
              <StatTile
                label="QIEA wall-clock vs NSGA-II"
                value={headline?.speedup ? `${num(headline.speedup, 2)}×` : '—'}
                unit={headline?.speedup ? 'faster' : undefined}
                foot="Mean across every instance and seed"
              />
              <StatTile
                label="Best hypervolume"
                value={headline ? `${headline.qieaHvWins} / ${headline.instanceCount}` : '—'}
                unit="instances"
                foot="Instances where QIEA has the highest mean hypervolume"
              />
              <StatTile label="Instances" value={num(data.instances.length)} foot={data.instances.join(' · ')} />
              <StatTile
                label="Runs recorded"
                value={num(rows.length)}
                foot={`${data.algorithms.length} algorithms × ${data.instances.length} instances × ${data.seeds.length} seeds`}
              />
            </div>

            <HypervolumeNote headline={headline} />

            <div className="filterbar">
              <SelectField
                label="Instance"
                value={instance}
                onChange={setInstance}
                options={[
                  { value: 'all', label: 'All instances' },
                  ...data.instances.map((i) => ({ value: i, label: INSTANCE_LABELS[i] || i })),
                ]}
                hint="Scopes every figure and the run table below."
              />
            </div>

            <div className="grid grid--2">
              <Figure
                title="Solution quality — hypervolume"
                subtitle="Mean archive hypervolume across seeds; higher is a better-covered trade-off surface"
                chart={
                  <GroupedColumnChart
                    groups={groups}
                    series={series}
                    height={260}
                    formatValue={(v) => num(v, 2)}
                    yLabel="Hypervolume"
                    ariaLabel="Mean hypervolume by algorithm and instance"
                  />
                }
                tableColumns={[
                  { key: 'instance', label: 'Instance' },
                  { key: 'algo', label: 'Algorithm' },
                  { key: 'hv', label: 'Hypervolume', align: 'right', render: (r) => num(r.hv, 4) },
                ]}
                tableRows={byInstance.filter((r) => visibleInstances.includes(r.instance))}
                tableCaption="Mean hypervolume per algorithm and instance."
                insight={
                  headline &&
                  `QIEA has the highest mean hypervolume on ${headline.qieaHvWins} of ${headline.instanceCount} instances.`
                }
              />

              <Figure
                title="Wall-clock time"
                subtitle="Mean seconds per run — the axis is time only, never shared with a quality metric"
                chart={
                  <GroupedColumnChart
                    groups={groups}
                    series={timeSeries}
                    height={260}
                    formatValue={(v) => `${num(v, 0)}s`}
                    yLabel="Seconds"
                    ariaLabel="Mean wall-clock seconds by algorithm and instance"
                  />
                }
                tableColumns={[
                  { key: 'instance', label: 'Instance' },
                  { key: 'algo', label: 'Algorithm' },
                  { key: 'wall_time_s', label: 'Seconds', align: 'right', render: (r) => num(r.wall_time_s, 2) },
                ]}
                tableRows={byInstance.filter((r) => visibleInstances.includes(r.instance))}
                tableCaption="Mean wall-clock seconds per algorithm and instance."
                insight={
                  headline?.speedup &&
                  `Averaged over every instance and seed, QIEA finishes ${num(headline.speedup, 2)}× ${headline.speedup >= 1 ? 'faster' : 'slower'} than NSGA-II.`
                }
              />
            </div>

            <Figure
              title="Archive size — front spread"
              subtitle="How many non-dominated solutions each algorithm retains; QIEA converges tightly rather than spreading a front"
              chart={
                <GroupedColumnChart
                  groups={groups}
                  series={archiveSeries}
                  height={240}
                  formatValue={(v) => num(v, 0)}
                  yLabel="Solutions in archive"
                  ariaLabel="Mean archive size by algorithm and instance"
                />
              }
              tableColumns={[
                { key: 'instance', label: 'Instance' },
                { key: 'algo', label: 'Algorithm' },
                { key: 'archive_size', label: 'Archive size', align: 'right', render: (r) => num(r.archive_size, 1) },
                { key: 'feasible_count', label: 'Feasible', align: 'right', render: (r) => num(r.feasible_count, 1) },
              ]}
              tableRows={byInstance.filter((r) => visibleInstances.includes(r.instance))}
              tableCaption="Mean archive size and feasible count per algorithm and instance."
              insight={archiveInsight(byInstance.filter((r) => visibleInstances.includes(r.instance)))}
            />

            <Disclosure
              title="Every recorded run"
              subtitle="one row per algorithm, instance and seed — the raw evidence behind the means above"
              count={`${rows.filter((r) => visibleInstances.includes(String(r.instance))).length} runs`}
            >
              <DataTable
                columns={[
                  { key: 'algo', label: 'Algorithm' },
                  { key: 'instance', label: 'Instance' },
                  { key: 'seed', label: 'Seed', align: 'right' },
                  { key: 'hv', label: 'Hypervolume', align: 'right', render: (r) => num(r.hv, 4) },
                  { key: 'igd', label: 'IGD', align: 'right', render: (r) => num(r.igd, 4) },
                  { key: 'archive_size', label: 'Archive', align: 'right' },
                  { key: 'feasible_count', label: 'Feasible', align: 'right' },
                  {
                    key: 'wall_time_s',
                    label: 'Seconds',
                    align: 'right',
                    render: (r) => num(r.wall_time_s, 2),
                  },
                ]}
                rows={rows.filter((r) => visibleInstances.includes(String(r.instance)))}
                rowKey={(r, i) => `${r.algo}-${r.instance}-${r.seed}-${i}`}
                highlight={(r) => r.algo === 'QIEA'}
                tall
              />
            </Disclosure>
          </>
        )}
      </div>
    </>
  )
}

/** Mean archive size of QIEA against the rest, in the visible instances. */
function archiveInsight(rows) {
  const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)
  const q = mean(rows.filter((r) => r.algo === 'QIEA').map((r) => r.archive_size))
  const others = mean(rows.filter((r) => r.algo !== 'QIEA').map((r) => r.archive_size))
  if (q == null || others == null) return null
  return `QIEA keeps ${num(q, 1)} solutions on average against ${num(others, 1)} for the other algorithms — a tight cluster, not a broad front.`
}

/**
 * State the benchmark honestly: on these committed results NSGA-II attains the
 * higher hypervolume, and QIEA's advantage is wall-clock time with a much
 * tighter archive. Reporting it as a clean win would misread the CSV.
 */
function HypervolumeNote({ headline }) {
  if (!headline || headline.qieaHvWins >= headline.instanceCount) return null
  const winners = Object.entries(headline.bestHvByInstance)
    .map(([inst, row]) => `${inst}: ${row.algo}`)
    .join(' · ')
  return (
    <div className="note">
      <Icon name="info" size={18} className="note__icon" />
      <span>
        <strong>QIEA leads on time, not on hypervolume here.</strong> On these committed results the
        highest mean hypervolume per instance is {winners}. QIEA finishes faster and keeps a far smaller
        archive — it converges to a tight cluster instead of spreading a broad front, which is why its
        archive-size column sits near 1.
      </span>
    </div>
  )
}
