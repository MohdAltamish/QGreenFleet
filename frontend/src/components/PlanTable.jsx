import { DataTable } from './DataTable'
import { fuelLabel, humanizeChange, num, titleCase } from '../lib/format'
import { fuelColor } from '../lib/palette'

/**
 * Per-vessel deployment plan with the change against business-as-usual.
 *
 * The fuel cell pairs a color swatch with the fuel name, so identity never
 * rests on hue alone.
 */
export function PlanTable({ plan, caption }) {
  const columns = [
    { key: 'vessel_id', label: 'Vessel' },
    { key: 'type', label: 'Type', render: (r) => titleCase(r.type) },
    {
      key: 'route_id',
      label: 'Route',
      render: (r) => (r.assigned ? r.route_id : <span className="muted">{r.route_id}</span>),
    },
    { key: 'speed_kn', label: 'Speed kn', align: 'right', render: (r) => num(r.speed_kn, 1) },
    { key: 'bau_speed_kn', label: 'BAU kn', align: 'right', render: (r) => num(r.bau_speed_kn, 1) },
    {
      key: 'speed_delta_kn',
      label: 'Δ kn',
      align: 'right',
      render: (r) => (r.speed_delta_kn ? num(r.speed_delta_kn, 1) : '—'),
    },
    {
      key: 'fuel',
      label: 'Fuel',
      render: (r) => (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span className="swatch" style={{ background: fuelColor(r.fuel) }} aria-hidden="true" />
          {fuelLabel(r.fuel)}
        </span>
      ),
    },
    {
      key: 'shore_power',
      label: 'Shore power',
      render: (r) => (r.shore_power ? <span className="tag">connected</span> : <span className="muted">—</span>),
    },
    { key: 'change_vs_bau', label: 'Change vs BAU', render: (r) => humanizeChange(r.change_vs_bau) },
  ]

  return (
    <DataTable
      columns={columns}
      rows={plan}
      caption={caption}
      rowKey={(r) => r.vessel_id}
      highlight={(r) => r.change_vs_bau !== 'no change'}
      tall
      emptyLabel="This solution carries no per-vessel plan."
    />
  )
}
