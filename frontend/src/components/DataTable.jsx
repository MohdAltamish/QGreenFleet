import { useState } from 'react'

/**
 * Table view — the WCAG-clean twin every chart on this dashboard ships with,
 * and the detail layer wherever raw rows are needed. Long tables paginate;
 * the wrap owns horizontal overflow so the page body never scrolls sideways.
 *
 * columns: [{ key, label, align, render?, className? }]
 */
export function DataTable({
  columns,
  rows,
  caption,
  rowKey,
  highlight,
  tall = false,
  emptyLabel = 'No rows.',
  pageSize = 12,
}) {
  const [page, setPage] = useState(0)
  if (!rows?.length) return <div className="states">{emptyLabel}</div>

  const pages = Math.ceil(rows.length / pageSize)
  // A filter can shrink the rows under the current page; clamp instead of resetting.
  const current = Math.min(page, pages - 1)
  const start = current * pageSize
  const visible = pages > 1 ? rows.slice(start, start + pageSize) : rows

  return (
    <>
    <div className={`table-wrap${tall ? ' table-wrap--tall' : ''}`}>
      <table className="data">
        {caption && <caption>{caption}</caption>}
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} scope="col" className={col.align === 'right' ? 'num' : undefined}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((row, j) => {
            const i = start + j
            return (
              <tr
                key={rowKey ? rowKey(row, i) : i}
                className={highlight?.(row, i) ? 'is-highlight' : undefined}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={[col.align === 'right' ? 'num' : '', col.className || '']
                      .filter(Boolean)
                      .join(' ') || undefined}
                  >
                    {col.render ? col.render(row, i) : row[col.key] ?? '—'}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
    {pages > 1 && (
      <nav className="pager" aria-label="Table pages">
        <span>
          Rows <span className="mono">{start + 1}–{Math.min(start + pageSize, rows.length)}</span> of{' '}
          <span className="mono">{rows.length}</span>
        </span>
        <span className="btn-row">
          <button type="button" className="btn btn--sm" disabled={current === 0} onClick={() => setPage(current - 1)}>
            Previous
          </button>
          <button
            type="button"
            className="btn btn--sm"
            disabled={current >= pages - 1}
            onClick={() => setPage(current + 1)}
          >
            Next
          </button>
        </span>
      </nav>
    )}
    </>
  )
}
