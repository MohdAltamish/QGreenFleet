import { useState } from 'react'
import { ViewToggle } from '../Field'
import { DataTable } from '../DataTable'
import { Panel } from '../Panel'

/**
 * A figure and its table twin in one panel.
 *
 * Every chart on this dashboard ships a WCAG-clean table equivalent, which is
 * also the relief for the light-mode series colors that sit below 3:1 against
 * the surface — no value is reachable only by hovering.
 */
export function Figure({
  title,
  subtitle,
  actions,
  chart,
  tableColumns,
  tableRows,
  tableCaption,
  refetching,
  insight,
}) {
  const [view, setView] = useState('chart')
  const hasTable = Boolean(tableColumns && tableRows)

  return (
    <Panel
      title={title}
      subtitle={subtitle}
      refetching={refetching}
      insight={insight}
      actions={
        <>
          {actions}
          {hasTable && (
            <ViewToggle
              value={view}
              onChange={setView}
              options={[
                { value: 'chart', label: 'Chart' },
                { value: 'table', label: 'Table' },
              ]}
            />
          )}
        </>
      }
    >
      {view === 'chart' || !hasTable ? (
        chart
      ) : (
        <DataTable columns={tableColumns} rows={tableRows} caption={tableCaption} tall />
      )}
    </Panel>
  )
}
