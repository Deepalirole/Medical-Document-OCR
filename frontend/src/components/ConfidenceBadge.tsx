import type { PrescriptionField } from '../types'

const styles = {
  HIGH: 'bg-emerald-100 text-emerald-800',
  MEDIUM: 'bg-amber-100 text-amber-800',
  LOW: 'bg-orange-100 text-orange-800',
  REVIEW_REQUIRED: 'bg-red-100 text-red-700',
}

export function ConfidenceBadge({ field }: { field: PrescriptionField }) {
  const label = field.review_status === 'REVIEW_REQUIRED' ? 'Review required' : field.review_status.toLowerCase()
  return <span className={`rounded-md px-2 py-1 font-mono text-[10px] font-medium uppercase tracking-wider ${styles[field.review_status]}`}>{label}{field.confidence !== null ? ` · ${Math.round(field.confidence * 100)}%` : ''}</span>
}

