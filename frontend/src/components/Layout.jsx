import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { IS_STATIC } from '../api/client'
import { useTheme } from '../hooks/useTheme'
import { num } from '../lib/format'
import { STATUS_LABEL, resolveSteps } from '../lib/workflow'
import { Pill } from './Field'
import { Icon } from './Icon'
import { TONE_ICON } from '../lib/palette'

/** Navigation mirrors the pipeline: each route carries its step number. */
const NAV = [
  { group: 'Workspace', items: [{ to: '/overview', label: 'Overview', icon: 'grid' }] },
  {
    group: 'Pipeline',
    items: [
      { to: '/fleet', label: 'Fleet & routes', icon: 'ship', step: 1 },
      { to: '/predict', label: 'Fuel predictor', icon: 'activity', step: 2 },
      { to: '/optimize', label: 'Optimization', icon: 'cpu', step: 3 },
      { to: '/scenarios', label: 'Policy scenarios', icon: 'sliders', step: 4 },
      { to: '/benchmark', label: 'Benchmarks', icon: 'bars', step: 4 },
      { to: '/reports', label: 'Reports & figures', icon: 'file', step: 5 },
    ],
  },
]

const ROUTE_LABEL = Object.fromEntries(
  NAV.flatMap((g) => g.items.map((i) => [i.to, { group: g.group, label: i.label }])),
)

const THEME_NEXT = { system: 'light', light: 'dark', dark: 'system' }
const THEME_ICON = { system: 'monitor', light: 'sun', dark: 'moon' }
const THEME_LABEL = { system: 'System theme', light: 'Light theme', dark: 'Dark theme' }

export function Layout({ health, healthPending, children }) {
  const { theme, cycle } = useTheme()
  const { pathname } = useLocation()
  // The drawer remembers the path it was opened on, so any navigation —
  // whichever control triggered it — closes it without an effect.
  const [openedOn, setOpenedOn] = useState(null)
  const drawerOpen = openedOn === pathname
  const setDrawerOpen = (open) => setOpenedOn(open ? pathname : null)

  useEffect(() => {
    if (!drawerOpen) return undefined
    const onKey = (e) => e.key === 'Escape' && setOpenedOn(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerOpen])

  const steps = resolveSteps(health, pathname, { pending: healthPending })
  const current = steps.find((s) => s.routes.includes(pathname))
  const crumb = ROUTE_LABEL[pathname]

  return (
    <div className={`shell${drawerOpen ? ' is-drawer-open' : ''}`}>
      <aside className="sidebar" id="sidebar" aria-label="Sidebar">
        <div className="sidebar__head">
          <Link to="/" className="brand">
            <span className="brand__mark" aria-hidden="true">
              <Icon name="leaf" size={18} strokeWidth={2} />
            </span>
            <span className="brand__text">
              <span className="brand__name">QGreenFleet</span>
              <span className="brand__sub">Fleet decarbonisation</span>
            </span>
          </Link>
          <button
            type="button"
            className="icon-btn sidebar__close"
            onClick={() => setDrawerOpen(false)}
            aria-label="Close navigation"
          >
            <Icon name="x" />
          </button>
        </div>

        <nav className="nav" aria-label="Main">
          {NAV.map((section) => (
            <div key={section.group} className="nav__group">
              <div className="nav__group-label">{section.group}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => `nav__link${isActive ? ' is-active' : ''}`}
                >
                  <Icon name={item.icon} size={17} />
                  <span className="nav__label">{item.label}</span>
                  {item.step && <span className="nav__step">{item.step}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <SystemStatus health={health} pending={healthPending} />
      </aside>

      <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)} aria-hidden="true" />

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="icon-btn topbar__menu"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation"
            aria-controls="sidebar"
            aria-expanded={drawerOpen}
          >
            <Icon name="menu" />
          </button>

          <nav className="crumbs" aria-label="Breadcrumb">
            <span className="crumbs__root">QGreenFleet</span>
            {crumb && (
              <>
                <Icon name="chevronRight" size={14} className="crumbs__sep" />
                <span className="crumbs__group">{crumb.group}</span>
                <Icon name="chevronRight" size={14} className="crumbs__sep" />
                <span className="crumbs__here" aria-current="page">
                  {crumb.label}
                </span>
              </>
            )}
          </nav>

          {current && (
            <span className={`step-chip step-chip--${current.status}`}>
              <span className="step-chip__n">
                Step {current.index + 1}/{steps.length}
              </span>
              <span className="step-chip__stage">{current.stage}</span>
              <span className="visually-hidden">— {STATUS_LABEL[current.status]}</span>
            </span>
          )}

          <div className="topbar__tools">
            <Notifications health={health} pending={healthPending} />
            <button
              type="button"
              className="icon-btn"
              onClick={cycle}
              aria-label={`${THEME_LABEL[theme]} — switch to ${THEME_LABEL[THEME_NEXT[theme]].toLowerCase()}`}
              title={THEME_LABEL[theme]}
            >
              <Icon name={THEME_ICON[theme]} />
            </button>
            <Profile health={health} />
          </div>
        </header>

        <div className="page" key={pathname}>
          {children}
        </div>
      </div>
    </div>
  )
}

/** Live backend status, pinned to the bottom of the sidebar. */
function SystemStatus({ health, pending }) {
  const rows = pending
    ? [{ tone: 'info', label: 'Checking API…' }]
    : !health
      ? [{ tone: 'critical', label: 'API offline' }]
      : [
          {
            tone: health.predictor?.available ? 'good' : 'critical',
            label: health.predictor?.available ? `Surrogate · ${health.predictor.model_name}` : 'Surrogate offline',
          },
          health.fleet?.loaded
            ? { tone: 'good', label: `${health.fleet.vessels} ships · ${health.fleet.routes} routes` }
            : { tone: 'critical', label: 'No active fleet' },
        ]

  return (
    <div className="sysstatus">
      <div className="sysstatus__head">
        <span className="nav__group-label">System</span>
        {health?.version && <span className="mono sysstatus__ver">v{health.version}</span>}
      </div>
      {IS_STATIC && <Pill tone="warning">Static demo · no live backend</Pill>}
      <ul className="sysstatus__list">
        {rows.map((r) => (
          <li key={r.label} className={`sysstatus__row tone--${r.tone}`}>
            <Icon name={TONE_ICON[r.tone]} size={15} />
            <span>{r.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Notices derived from the real /health payload — nothing is invented. */
function noticesFor(health, pending) {
  if (pending) return []
  if (!health) {
    return [{ tone: 'critical', title: 'API unreachable', body: 'Start it with: uvicorn src.api.main:app --port 8000' }]
  }
  const out = []
  if (IS_STATIC) {
    out.push({ tone: 'info', title: 'Static snapshot', body: 'Live optimisation, fleet changes and PDF downloads need the FastAPI backend.' })
  }
  const p = health.predictor
  if (p && !p.available) {
    out.push({ tone: 'critical', title: 'Surrogate offline', body: p.error || 'No trained model on disk.' })
  } else if (p?.metrics?.test_mape > 25) {
    out.push({
      tone: 'warning',
      title: 'Low surrogate accuracy',
      body: `Test MAPE is ${num(p.metrics.test_mape, 1)}% — treat single fuel predictions as indicative.`,
    })
  }
  if (health.fleet?.loaded === false) {
    out.push({ tone: 'critical', title: 'No active fleet', body: health.fleet.error || 'Load a fleet to continue.' })
  } else if (health.fleet?.loaded) {
    out.push({ tone: 'good', title: 'Fleet active', body: `${health.fleet.source} — ${health.fleet.vessels} ships, ${health.fleet.routes} routes.` })
  }
  return out
}

function Notifications({ health, pending }) {
  const notices = noticesFor(health, pending)
  const alerts = notices.filter((n) => n.tone === 'warning' || n.tone === 'critical').length
  return (
    <>
      <button
        type="button"
        className="icon-btn"
        popoverTarget="notifications"
        aria-label={`Notifications${alerts ? ` — ${alerts} need attention` : ''}`}
      >
        <Icon name="bell" />
        {alerts > 0 && <span className="icon-btn__badge mono">{alerts}</span>}
      </button>
      <div id="notifications" popover="auto" className="popover">
        <div className="popover__head">Notifications</div>
        {notices.length === 0 ? (
          <div className="popover__empty">Nothing to report.</div>
        ) : (
          <ul className="popover__list">
            {notices.map((n) => (
              <li key={n.title} className={`notice tone--${n.tone}`}>
                <Icon name={TONE_ICON[n.tone]} size={16} />
                <span>
                  <span className="notice__title">{n.title}</span>
                  <span className="notice__body">{n.body}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  )
}

function Profile({ health }) {
  return (
    <>
      <button type="button" className="avatar" popoverTarget="profile" aria-label="Workspace profile">
        <Icon name="user" size={16} />
      </button>
      <div id="profile" popover="auto" className="popover popover--narrow">
        <div className="popover__head">Local workspace</div>
        <p className="popover__text">
          No user accounts are configured for this dashboard — every visitor shares one workspace.
        </p>
        <dl className="kv kv--compact">
          <dt>Mode</dt>
          <dd>{IS_STATIC ? 'Static snapshot' : 'Live API'}</dd>
          <dt>API version</dt>
          <dd className="mono">{health?.version ?? '—'}</dd>
        </dl>
      </div>
    </>
  )
}

/** Page header: title, one-line description, status badge and actions. */
export function PageHeader({ title, subtitle, actions, status }) {
  return (
    <header className="page-head">
      <div className="page-head__titles">
        <h1>{title}</h1>
        {subtitle && <p className="page-head__sub">{subtitle}</p>}
      </div>
      {(status || actions) && (
        <div className="page-head__actions">
          {status && <Pill tone={status.tone}>{status.label}</Pill>}
          {actions}
        </div>
      )}
    </header>
  )
}
