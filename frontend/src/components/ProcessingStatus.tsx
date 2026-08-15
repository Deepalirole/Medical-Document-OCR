import { AlertTriangle, CheckCircle2, LoaderCircle, ShieldCheck } from 'lucide-react'

import type { ProcessingStatus as Status } from '../types'

export function ProcessingStatus({ status }: { status: Status | null }) {
  if (!status) return <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Waiting to process…</div>
  const isFailureStatus = status.status.endsWith('_FAILED') || status.status === 'ERROR'
  const latestFailedJob = [...status.jobs].reverse().find((job) => job.status === 'FAILED')
  const failed = isFailureStatus ? latestFailedJob : null
  const isApproved = status.status === 'APPROVED'
  const isReviewRequired = status.status === 'REVIEW_REQUIRED' || status.status === 'COMPLETED'

  return (
    <div
      className={`rounded-xl border p-4 ${
        failed
          ? 'border-red-200 bg-red-50'
          : isApproved
            ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
            : isReviewRequired
              ? 'border-emerald-200 bg-emerald-50'
              : 'border-amber-200 bg-amber-50'
      }`}
    >
      <div className="flex items-center gap-3">
        {failed ? (
          <AlertTriangle className="text-red-600" size={19} />
        ) : isApproved ? (
          <ShieldCheck className="text-emerald-700" size={19} />
        ) : isReviewRequired ? (
          <CheckCircle2 className="text-evergreen" size={19} />
        ) : (
          <LoaderCircle className="animate-spin text-amber-700" size={19} />
        )}
        <div>
          <p className="text-sm font-semibold">{failed ? failed.error_code : status.status.replaceAll('_', ' ')}</p>
          <p className="text-xs text-slate-500">
            {failed?.safe_error_message ||
              (isApproved
                ? 'Immutable approved version snapshot preserved'
                : `${status.jobs.length} recorded processing job${status.jobs.length === 1 ? '' : 's'}`)}
          </p>
        </div>
      </div>
    </div>
  )
}


