import { CheckCheck, CheckSquare, Loader2 } from 'lucide-react'
import { useState } from 'react'

import { api } from '../lib/api'
import type { ApprovedVersion, FieldsResponse } from '../types'

export function ReviewActions({
  prescriptionId,
  fields,
  isApproved,
  onApproved,
  onChanged,
}: {
  prescriptionId: string
  fields: FieldsResponse | null
  isApproved?: boolean
  onApproved: (version: ApprovedVersion) => void
  onChanged?: () => void
}) {
  const [approving, setApproving] = useState(false)
  const [confirmingAll, setConfirmingAll] = useState(false)
  const [actionError, setActionError] = useState('')

  const reviewRequiredFields =
    fields?.fields.filter((field) => field.review_status === 'REVIEW_REQUIRED') || []
  const hasFields = (fields?.fields.length || 0) > 0
  const unresolved = reviewRequiredFields.length > 0 || !hasFields

  async function handleConfirmAll() {
    if (!fields || reviewRequiredFields.length === 0) return
    setConfirmingAll(true)
    setActionError('')
    try {
      const updates = reviewRequiredFields.map((field) => [
        field.id,
        field.current_value,
        'Bulk reviewer confirmation',
      ] as [string, unknown, string | null])
      await api.mutateFields(prescriptionId, { updates })
      onChanged?.()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not confirm all fields.')
    } finally {
      setConfirmingAll(false)
    }
  }

  async function handleApprove() {
    setApproving(true)
    setActionError('')
    try {
      const version = await api.approve(prescriptionId)
      onApproved(version)
      onChanged?.()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Approval failed.')
    } finally {
      setApproving(false)
    }
  }

  if (isApproved) {
    return (
      <div className="inline-flex items-center gap-2 rounded-xl border border-emerald-300 bg-emerald-100/90 px-4 py-2.5 text-xs font-semibold text-emerald-900 shadow-sm">
        <CheckCheck size={16} className="text-emerald-700" />
        <span>Version Approved & Locked</span>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {unresolved && hasFields && (
        <button
          disabled={confirmingAll || approving}
          className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-900 shadow-sm transition hover:bg-amber-100 disabled:opacity-50"
          onClick={() => void handleConfirmAll()}
          title="Mark all review-required fields as confirmed"
        >
          {confirmingAll ? <Loader2 size={16} className="animate-spin" /> : <CheckSquare size={16} />}
          <span>Confirm all ({reviewRequiredFields.length})</span>
        </button>
      )}

      <button
        disabled={unresolved || approving}
        className="inline-flex items-center justify-center gap-2 rounded-xl bg-evergreen px-5 py-3 font-semibold text-white shadow-sm transition hover:bg-ink disabled:cursor-not-allowed disabled:opacity-40"
        onClick={() => void handleApprove()}
        title={
          unresolved
            ? `Review or confirm ${reviewRequiredFields.length} field${reviewRequiredFields.length === 1 ? '' : 's'} to approve`
            : 'Approve version and create immutable audit snapshot'
        }
      >
        {approving ? <Loader2 size={18} className="animate-spin" /> : <CheckCheck size={18} />}
        <span>{approving ? 'Approving…' : 'Approve version'}</span>
      </button>

      {actionError && (
        <span className="text-xs text-red-600 font-medium">{actionError}</span>
      )}
    </div>
  )
}


