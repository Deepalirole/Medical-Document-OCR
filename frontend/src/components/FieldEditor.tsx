import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'

import { api } from '../lib/api'
import type { PrescriptionField } from '../types'
import { ConfidenceBadge } from './ConfidenceBadge'

function displayValue(value: unknown) {
  if (value === null || value === undefined) return ''
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function parseValue(value: string, type: string): unknown {
  if (!value.trim()) return null
  if (type === 'number') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : value
  }
  if (type === 'boolean') return value === 'true'
  if (type === 'key_value') {
    try { return JSON.parse(value) as unknown } catch { return value }
  }
  return value
}

export function FieldEditor({ prescriptionId, field, label, onSaved }: { prescriptionId: string; field: PrescriptionField; label: string; onSaved: () => void }) {
  const [value, setValue] = useState(displayValue(field.current_value))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => setValue(displayValue(field.current_value)), [field.current_value])
  const dirty = value !== displayValue(field.current_value)

  async function save() {
    setSaving(true)
    setError('')
    try {
      await api.correctField(
        prescriptionId,
        field.id,
        parseValue(value, field.field_type),
        dirty ? 'Reviewer correction' : 'Reviewer confirmed',
      )
      onSaved()
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save field.')
    } finally {
      setSaving(false)
    }
  }

  const needsReview = field.review_status === 'REVIEW_REQUIRED'
  const canAct = (dirty || needsReview) && !saving

  return (
    <div
      className={`rounded-xl border p-3.5 transition-colors ${
        needsReview ? 'border-amber-300 bg-amber-50/50' : 'border-slate-200 bg-white'
      }`}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <label htmlFor={field.id} className="text-xs font-semibold uppercase tracking-wide text-slate-700">
          {label.replaceAll('_', ' ')}
        </label>
        <ConfidenceBadge field={field} />
      </div>
      <div className="flex gap-2">
        {field.field_type === 'free_text' ? (
          <textarea
            id={field.id}
            rows={3}
            className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-evergreen focus:outline-none focus:ring-1 focus:ring-evergreen"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        ) : (
          <input
            id={field.id}
            type={field.field_type === 'date' ? 'date' : field.field_type === 'number' ? 'number' : 'text'}
            className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-evergreen focus:outline-none focus:ring-1 focus:ring-evergreen"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        )}
        <button
          aria-label={dirty ? `Save ${label}` : `Confirm ${label}`}
          disabled={!canAct}
          className={`inline-flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-semibold text-white shadow-sm transition disabled:opacity-30 ${
            dirty ? 'bg-evergreen hover:bg-ink' : needsReview ? 'bg-amber-600 hover:bg-amber-700' : 'bg-slate-300'
          }`}
          onClick={() => void save()}
          title={dirty ? 'Save correction' : needsReview ? 'Confirm extracted value' : 'Saved'}
        >
          <Save size={15} />
          <span>{saving ? '…' : dirty ? 'Save' : needsReview ? 'Confirm' : 'Saved'}</span>
        </button>
      </div>
      {field.original_value !== field.current_value && (
        <p className="mt-2 text-[11px] text-slate-500">
          Machine value: {displayValue(field.original_value) || 'empty'}
        </p>
      )}
      {!!field.evidence?.length && (
        <p className="mt-2 text-[11px] text-evergreen">
          {field.evidence.length} evidence link{field.evidence.length === 1 ? '' : 's'} preserved
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}

