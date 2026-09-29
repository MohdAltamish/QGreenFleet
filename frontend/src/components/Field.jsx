/** Labelled form controls used by the filter bars and parameter panels. */
import { TONE_ICON } from '../lib/palette'
import { Icon } from './Icon'

export function SliderField({ label, value, display, min, max, step = 1, onChange, hint }) {
  return (
    <label className="field">
      <span className="field__label">
        <span>{label}</span>
        <span className="field__value">{display ?? value}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}

export function SelectField({ label, value, onChange, options, hint }) {
  return (
    <label className="field">
      <span className="field__label">
        <span>{label}</span>
      </span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}

export function NumberField({ label, value, onChange, min, max, step = 1, hint }) {
  return (
    <label className="field">
      <span className="field__label">
        <span>{label}</span>
      </span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}

/** Two-state view switch used to flip a figure to its table twin. */
export function ViewToggle({ value, onChange, options }) {
  return (
    <div className="segmented" role="group" aria-label="View">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className="segmented__btn"
          aria-pressed={value === opt.value}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

export function Pill({ tone = 'neutral', children }) {
  return (
    <span className={`pill${tone !== 'neutral' ? ` pill--${tone}` : ''}`}>
      {TONE_ICON[tone] && <Icon name={TONE_ICON[tone]} size={13} strokeWidth={2} />}
      {children}
    </span>
  )
}
