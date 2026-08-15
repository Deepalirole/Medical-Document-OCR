import {
  CheckCheck,
  ChevronDown,
  ChevronUp,
  Filter,
  Info,
  Loader2,
  RotateCcw,
  Search,
  Sparkles,
  ThumbsUp,
  Trash2,
} from 'lucide-react'
import { useMemo, useState } from 'react'

import { api } from '../lib/api'
import type { FieldsResponse, PrescriptionField } from '../types'

interface SchemaNode {
  key: string
  type: string
  fields?: SchemaNode[]
  item_schema?: Record<string, { type: string; required?: boolean }>
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function formatSectionTitle(key: string): string {
  const titles: Record<string, string> = {
    patient: 'Patient Information',
    doctor: 'Treating Clinician',
    complaints: 'Primary Chief Complaint',
    physical_examination: 'Physical Examination & Vitals',
    diagnosis: 'Clinical Diagnosis',
    medical_history: 'Medical & Drug History',
    medicines: 'Prescribed Remedies',
    follow_up: 'Patient Advice & Follow-Up',
  }
  return titles[key] || key.replaceAll('_', ' ')
}

function formatFieldLabel(fieldPath: string): string {
  const match = fieldPath.match(/^([a-zA-Z0-9_]+)\[(\d+)\]\.(.+)$/)
  if (match) {
    const [, section, index, prop] = match
    const sectionName = section === 'medicines' ? 'Medicine' : section.replaceAll('_', ' ')
    const propName = prop.replaceAll('_', ' ')
    return `${sectionName} #${Number(index) + 1} · ${propName}`
  }
  if (fieldPath.includes('.')) {
    return fieldPath
      .split('.')
      .map((p) => p.replaceAll('_', ' '))
      .join(' · ')
  }
  return fieldPath.replaceAll('_', ' ')
}

function parseValue(value: string, type: string): unknown {
  if (!value.trim()) return null
  if (type === 'number') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : value
  }
  if (type === 'boolean') return value === 'true'
  if (type === 'key_value') {
    try {
      return JSON.parse(value) as unknown
    } catch {
      return value
    }
  }
  return value
}

export function ReviewMatrix({
  prescriptionId,
  fieldsData,
  activePageIndex,
  isProcessing,
  onRunExtraction,
  onChanged,
}: {
  prescriptionId: string
  fieldsData: FieldsResponse | null
  activePageIndex: number
  isProcessing?: boolean
  onRunExtraction?: () => void
  onChanged: () => void
}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedSection, setSelectedSection] = useState('ALL')
  const [selectedStatus, setSelectedStatus] = useState('ALL')
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    patient: true,
    medicines: true,
    doctor: true,
    complaints: true,
    physical_examination: true,
    diagnosis: true,
    medical_history: true,
    follow_up: true,
  })
  const [pendingValues, setPendingValues] = useState<Record<string, string>>({})
  const [savingFieldId, setSavingFieldId] = useState<string | null>(null)
  const [isBatchAccepting, setIsBatchAccepting] = useState(false)
  const [evidencePopup, setEvidencePopup] = useState<{
    fieldPath: string
    evidence: PrescriptionField['evidence']
  } | null>(null)

  const rawFields = useMemo(() => fieldsData?.fields || [], [fieldsData?.fields])

  // Derived filter list
  const filteredFields = useMemo(() => {
    return rawFields.filter((field) => {
      // 1. Search Query Filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matchPath = field.field_path.toLowerCase().includes(q)
        const matchVal = displayValue(field.current_value).toLowerCase().includes(q)
        if (!matchPath && !matchVal) return false
      }

      // 2. Section Filter
      if (selectedSection !== 'ALL') {
        if (!field.field_path.startsWith(selectedSection)) return false
      }

      // 3. Review Status Filter
      if (selectedStatus !== 'ALL') {
        if (field.review_status !== selectedStatus) return false
      }

      return true
    })
  }, [rawFields, searchQuery, selectedSection, selectedStatus])

  // Extract unique top-level schema sections
  const sections = useMemo(() => {
    const schemaDef = (fieldsData?.schema_definition || {}) as { sections?: SchemaNode[] }
    return schemaDef.sections || []
  }, [fieldsData])

  const sectionKeys = useMemo(() => {
    return sections.map((s) => s.key)
  }, [sections])

  // Quick single-field confirm
  async function handleConfirmField(field: PrescriptionField) {
    const valStr = pendingValues[field.id]
    const nextVal = valStr !== undefined ? parseValue(valStr, field.field_type) : field.current_value
    setSavingFieldId(field.id)
    try {
      await api.correctField(prescriptionId, field.id, nextVal, 'Field value confirmed')
      setPendingValues((prev) => {
        const next = { ...prev }
        delete next[field.id]
        return next
      })
      onChanged()
    } finally {
      setSavingFieldId(null)
    }
  }

  // Quick reset to original machine value
  async function handleResetField(field: PrescriptionField) {
    setSavingFieldId(field.id)
    try {
      await api.correctField(prescriptionId, field.id, field.original_value, 'Reset to machine value')
      setPendingValues((prev) => {
        const next = { ...prev }
        delete next[field.id]
        return next
      })
      onChanged()
    } finally {
      setSavingFieldId(null)
    }
  }

  // Mark all filtered fields as accepted
  async function handleAcceptAllFiltered() {
    setIsBatchAccepting(true)
    try {
      const candidateList = filteredFields.length > 0 ? filteredFields : rawFields
      const toConfirm = candidateList.filter((f) => f.review_status !== 'HIGH')
      const targetList = toConfirm.length > 0 ? toConfirm : candidateList
      if (targetList.length === 0) return
      const updates = targetList.map(
        (f) => [f.id, f.current_value, 'Batch accepted by reviewer'] as [string, unknown, string | null],
      )
      await api.mutateFields(prescriptionId, { updates })
      onChanged()
    } finally {
      setIsBatchAccepting(false)
    }
  }

  // Remove an entire array item / table row
  async function handleRemoveArrayItem(arrayItemId: string) {
    await api.mutateFields(prescriptionId, {
      remove_item_ids: [arrayItemId],
    })
    onChanged()
  }

  const toggleSection = (key: string) => {
    setExpandedSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  if (!fieldsData || rawFields.length === 0) {
    return (
      <div className="flex h-full min-h-96 flex-col items-center justify-center rounded-2xl bg-white p-8 text-center">
        <div className="max-w-md">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-mint text-evergreen">
            <Sparkles size={28} />
          </div>
          <h3 className="text-lg font-bold text-ink">Clinical Extraction Ready</h3>
          <p className="mt-2 text-xs leading-5 text-slate-500">
            This prescription document has been uploaded. Run the clinical extraction pipeline to
            automatically extract patient demographics, vitals, examination findings, diagnosis, and
            prescribed remedies.
          </p>
          {onRunExtraction && (
            <button
              onClick={onRunExtraction}
              disabled={isProcessing}
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-evergreen px-6 py-3 text-xs font-bold text-white shadow-sm transition hover:bg-ink active:scale-95 disabled:opacity-50 cursor-pointer"
            >
              <Sparkles size={16} />
              <span>{isProcessing ? 'Extracting clinical records…' : 'Run Clinical Extraction'}</span>
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Top Filter & Search Matrix Bar */}
      <div className="border-b border-slate-200 p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Search Box */}
          <div className="relative min-w-48 flex-1">
            <Search className="absolute left-3 top-2.5 text-slate-400" size={14} />
            <input
              type="text"
              placeholder="Search fields or values…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-2 pl-9 pr-3 text-xs text-ink placeholder:text-slate-400 focus:border-evergreen focus:bg-white focus:outline-none focus:ring-1 focus:ring-evergreen"
            />
          </div>

          {/* Section Filter */}
          <div className="flex items-center rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 shadow-sm">
            <Filter size={13} className="text-slate-400 mr-1.5" />
            <select
              aria-label="Filter by section"
              value={selectedSection}
              onChange={(e) => setSelectedSection(e.target.value)}
              className="bg-transparent text-xs font-semibold text-slate-700 focus:outline-none cursor-pointer"
            >
              <option value="ALL">All sections</option>
              {sectionKeys.map((k) => (
                <option key={k} value={k}>
                  {k.replaceAll('_', ' ')}
                </option>
              ))}
            </select>
          </div>

          {/* Status Filter */}
          <div className="flex items-center rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 shadow-sm">
            <select
              aria-label="Filter by review status"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="bg-transparent text-xs font-semibold text-slate-700 focus:outline-none cursor-pointer"
            >
              <option value="ALL">All statuses</option>
              <option value="REVIEW_REQUIRED">Needs review</option>
              <option value="HIGH">High confidence</option>
              <option value="EDITED">Edited</option>
            </select>
          </div>
        </div>
      </div>

      {/* Field Groups / Sections Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {sections.map((section) => {
          const sectionFields = filteredFields.filter((f) => f.field_path.startsWith(section.key))
          if (sectionFields.length === 0 && selectedSection !== 'ALL') return null

          const isExpanded = expandedSections[section.key] !== false
          const needsReviewCount = sectionFields.filter(
            (f) => f.review_status === 'REVIEW_REQUIRED',
          ).length

          return (
            <div
              key={section.key}
              className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm"
            >
              {/* Section Header */}
              <button
                onClick={() => toggleSection(section.key)}
                className="flex w-full items-center justify-between bg-slate-50/80 px-4 py-3 text-left transition hover:bg-slate-100/70"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    {formatSectionTitle(section.key)}
                  </span>
                  <span className="rounded-full bg-slate-200/80 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-600">
                    {sectionFields.length}
                  </span>
                  {needsReviewCount > 0 && (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 font-mono text-[10px] font-bold text-amber-800">
                      {needsReviewCount} needs review
                    </span>
                  )}
                </div>

                <div className="text-slate-400">
                  {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </div>
              </button>

              {/* Section Content */}
              {isExpanded && (
                <div className="divide-y divide-slate-100 p-2 space-y-1">
                  {sectionFields.map((field) => {
                    const isSaving = savingFieldId === field.id
                    const currentValStr =
                      pendingValues[field.id] !== undefined
                        ? pendingValues[field.id]
                        : displayValue(field.current_value)
                    const isDirty =
                      pendingValues[field.id] !== undefined &&
                      pendingValues[field.id] !== displayValue(field.current_value)
                    const isReviewReq = field.review_status === 'REVIEW_REQUIRED'
                    const conf = field.confidence !== null ? Math.round(field.confidence * 100) : null
                    const fieldLabel = formatFieldLabel(field.field_path)

                    return (
                      <div
                        key={field.id}
                        className={`group flex flex-col gap-2 rounded-xl p-3 transition sm:flex-row sm:items-center sm:justify-between ${
                          isReviewReq ? 'bg-amber-50/40' : 'hover:bg-slate-50/50'
                        }`}
                      >
                        {/* Field Label & Tags */}
                        <div className="min-w-44 sm:w-52">
                          <label
                            htmlFor={`field-input-${field.id}`}
                            className="block text-xs font-semibold text-slate-700 truncate"
                            title={fieldLabel}
                          >
                            {fieldLabel}
                          </label>
                          <div className="mt-1 flex items-center gap-1.5">
                            {/* Confidence / Status Pill */}
                            <span
                              className={`inline-flex items-center rounded-md px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                                isReviewReq
                                  ? 'bg-amber-100 text-amber-800'
                                  : conf !== null && conf >= 85
                                    ? 'bg-emerald-100 text-emerald-800'
                                    : 'bg-blue-100 text-blue-800'
                              }`}
                            >
                              {isReviewReq ? 'Needs Review' : conf !== null ? `Mapped ${conf}%` : 'Extracted'}
                            </span>

                            {/* Page Tag */}
                            {field.evidence && field.evidence[0] && (
                              <span className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[9px] font-semibold text-slate-500">
                                P{activePageIndex + 1}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Editable Value Control */}
                        <div className="flex-1">
                          {field.field_type === 'free_text' || currentValStr.length > 55 ? (
                            <textarea
                              id={`field-input-${field.id}`}
                              rows={2}
                              value={currentValStr}
                              onChange={(e) =>
                                setPendingValues((prev) => ({
                                  ...prev,
                                  [field.id]: e.target.value,
                                }))
                              }
                              onBlur={() => {
                                if (isDirty) void handleConfirmField(field)
                              }}
                              className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-ink shadow-sm transition focus:border-evergreen focus:outline-none focus:ring-1 focus:ring-evergreen"
                            />
                          ) : (
                            <input
                              id={`field-input-${field.id}`}
                              type={field.field_type === 'number' ? 'number' : 'text'}
                              value={currentValStr}
                              onChange={(e) =>
                                setPendingValues((prev) => ({
                                  ...prev,
                                  [field.id]: e.target.value,
                                }))
                              }
                              onBlur={() => {
                                if (isDirty) void handleConfirmField(field)
                              }}
                              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-ink shadow-sm transition focus:border-evergreen focus:outline-none focus:ring-1 focus:ring-evergreen"
                            />
                          )}
                        </div>

                        {/* Quick Action Matrix Buttons */}
                        <div className="flex items-center gap-1">
                          {/* Confirm / Save (Thumbs Up) */}
                          <button
                            onClick={() => void handleConfirmField(field)}
                            disabled={isSaving}
                            title={isDirty ? 'Save edit' : 'Confirm value'}
                            className={`rounded-lg p-1.5 transition shadow-sm ${
                              isDirty
                                ? 'bg-evergreen text-white hover:bg-ink'
                                : isReviewReq
                                  ? 'bg-amber-500 text-white hover:bg-amber-600'
                                  : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'
                            }`}
                          >
                            <ThumbsUp size={14} />
                          </button>

                          {/* Reset to machine extraction */}
                          {field.original_value !== field.current_value && (
                            <button
                              onClick={() => void handleResetField(field)}
                              disabled={isSaving}
                              title="Reset to machine value"
                              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                            >
                              <RotateCcw size={14} />
                            </button>
                          )}

                          {/* Evidence Preview / Info */}
                          {field.evidence && field.evidence.length > 0 && (
                            <button
                              onClick={() =>
                                setEvidencePopup({
                                  fieldPath: field.field_path,
                                  evidence: field.evidence,
                                })
                              }
                              title="View OCR evidence lineage"
                              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-evergreen"
                            >
                              <Info size={14} />
                            </button>
                          )}

                          {/* Delete Item (for array fields) */}
                          {field.array_item_id && (
                            <button
                              onClick={() => {
                                if (field.array_item_id)
                                  void handleRemoveArrayItem(field.array_item_id)
                              }}
                              title="Delete this array item"
                              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-600"
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}

                  {sectionFields.length === 0 && (
                    <p className="py-3 text-center text-xs text-slate-400">
                      No matching fields in this section.
                    </p>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Bottom Matrix Action Bar */}
      <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50/80 px-4 py-3">
        <span className="text-xs text-slate-500">
          {Object.keys(pendingValues).length > 0
            ? `${Object.keys(pendingValues).length} pending edit(s)`
            : 'No unsaved changes'}
        </span>

        <div className="flex items-center gap-2">
          {Object.keys(pendingValues).length > 0 && (
            <button
              onClick={() => setPendingValues({})}
              className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm hover:bg-slate-50"
            >
              Discard Changes
            </button>
          )}

          <button
            onClick={() => void handleAcceptAllFiltered()}
            disabled={isBatchAccepting}
            className="inline-flex items-center gap-1.5 rounded-xl bg-evergreen px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-ink active:scale-95 disabled:opacity-50 cursor-pointer"
          >
            {isBatchAccepting ? <Loader2 size={12} className="animate-spin" /> : <CheckCheck size={12} />}
            <span>{isBatchAccepting ? 'Accepting…' : 'Mark All Accepted'}</span>
          </button>
        </div>
      </div>

      {/* Evidence Lineage Modal / Popup */}
      {evidencePopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-evergreen">
                  OCR Lineage & Evidence
                </p>
                <p className="text-sm font-semibold text-ink">{evidencePopup.fieldPath}</p>
              </div>
              <button
                onClick={() => setEvidencePopup(null)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 max-h-64 overflow-y-auto space-y-2">
              {evidencePopup.evidence?.map((item, idx) => {
                const confVal = typeof item.confidence === 'number' ? Math.round(item.confidence * 100) : null
                return (
                  <div key={idx} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                    <div className="flex items-center justify-between text-[11px] font-mono text-slate-500">
                      <span>Engine: {String(item.engine || 'OCR')}</span>
                      <span>Conf: {confVal !== null ? `${confVal}%` : 'N/A'}</span>
                    </div>
                    <p className="mt-1 font-mono text-xs font-bold text-ink bg-white p-2 rounded border border-slate-200">
                      "{String(item.text || '')}"
                    </p>
                  </div>
                )
              })}
            </div>

            <div className="mt-4 text-right">
              <button
                onClick={() => setEvidencePopup(null)}
                className="rounded-xl bg-evergreen px-4 py-2 text-xs font-semibold text-white"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
