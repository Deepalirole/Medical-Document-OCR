import { AlertTriangle, CheckCircle2 } from 'lucide-react'

import type { FieldsResponse } from '../types'

export function ValidationPanel({ data }: { data: FieldsResponse | null }) {
  const review = data?.fields.filter((field) => field.review_status === 'REVIEW_REQUIRED') || []
  const warnings = data?.fields.flatMap((field) => (field.validation.warnings || []).map((warning) => ({ field: field.field_path, warning }))) || []
  if (!data) return null
  return <section className={`rounded-2xl border p-4 ${review.length ? 'border-red-200 bg-red-50' : 'border-emerald-200 bg-emerald-50'}`}><div className="flex items-center gap-3">{review.length ? <AlertTriangle className="text-red-600" /> : <CheckCircle2 className="text-evergreen" />}<div><p className="font-semibold">{review.length ? `${review.length} field${review.length === 1 ? '' : 's'} need review` : 'Review checks resolved'}</p><p className="text-xs text-slate-500">{warnings.length} validation warning{warnings.length === 1 ? '' : 's'}</p></div></div>{warnings.length > 0 && <ul className="mt-3 space-y-1 text-xs text-slate-600">{warnings.slice(0, 8).map((item) => <li key={`${item.field}-${item.warning}`}>{item.field}: {item.warning.replaceAll('_', ' ').toLowerCase()}</li>)}</ul>}</section>
}

