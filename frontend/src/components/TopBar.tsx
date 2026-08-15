import {
  CheckCheck,
  CheckSquare,
  Cpu,
  Download,
  FileText,
  Loader2,
  Play,
  Save,
  ShieldCheck,
} from 'lucide-react'

import type { FieldsResponse, OCRResponse, PrescriptionDetail, ProcessingStatus } from '../types'

export function TopBar({
  prescription,
  processingStatus,
  ocr,
  fields,
  isApproved: propsIsApproved,
  isProcessing,
  dirtyCount,
  onRunOCR,
  onSaveCorrections,
  onConfirmAll,
  onApprove,
  onExport,
}: {
  prescription: PrescriptionDetail | null
  processingStatus?: ProcessingStatus | null
  ocr: OCRResponse | null
  fields: FieldsResponse | null
  isApproved?: boolean
  isProcessing: boolean
  dirtyCount: number
  onRunOCR: () => void
  onSaveCorrections: () => void
  onConfirmAll: () => void
  onApprove: () => void
  onExport: () => void
}) {
  const isApproved = propsIsApproved ?? (prescription?.status === 'APPROVED')
  const isReviewRequired = prescription?.status === 'REVIEW_REQUIRED'
  const isUploaded = prescription?.status === 'UPLOADED'

  const reviewRequiredFields =
    fields?.fields.filter((field) => field.review_status === 'REVIEW_REQUIRED') || []

  // Calculate OCR character count
  const totalChars =
    ocr?.results.reduce((acc, curr) => acc + (curr.raw_text?.length || 0), 0) || 0
  const avgConfidence =
    ocr?.results && ocr.results.length > 0
      ? Math.round(
          (ocr.results.reduce((acc, curr) => acc + (curr.confidence || 0), 0) /
            ocr.results.length) *
            100,
        )
      : null

  return (
    <header className="sticky top-0 z-20 flex h-16 w-full items-center justify-between border-b border-slate-200 bg-white/95 px-6 backdrop-blur">
      {/* Left: Breadcrumbs & Document Title */}
      <div className="flex items-center gap-3 truncate">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-evergreen/10 text-evergreen">
          <FileText size={18} />
        </div>
        <div className="truncate">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            <span>PRESCRIPTION INTELLIGENCE</span>
            <span>/</span>
            <span className="text-evergreen">Document Review</span>
          </div>
          <p className="truncate text-sm font-bold text-ink">
            {prescription?.original_filename || 'No document selected'}
          </p>
        </div>
      </div>

      {/* Center: Live Intelligence Badges */}
      {prescription && (
        <div className="hidden items-center gap-2.5 lg:flex">
          {/* Status Badge */}
          <div
            title={
              processingStatus?.jobs?.length
                ? `${processingStatus.jobs.length} processing job(s) recorded`
                : undefined
            }
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
              isApproved
                ? 'bg-emerald-100 text-emerald-800'
                : isReviewRequired
                  ? 'bg-amber-100 text-amber-800'
                  : isUploaded
                    ? 'bg-slate-100 text-slate-700'
                    : 'bg-blue-100 text-blue-800'
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                isApproved
                  ? 'bg-emerald-500'
                  : isReviewRequired
                    ? 'bg-amber-500'
                    : isUploaded
                      ? 'bg-slate-400'
                      : 'bg-blue-500 animate-pulse'
              }`}
            />
            <span>{prescription.status.replaceAll('_', ' ')}</span>
          </div>

          {/* Engine Badge */}
          <div className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 font-mono text-[11px] font-medium text-slate-700">
            <Cpu size={13} className="text-slate-500" />
            <span>TESSERACT 5.4 + LLM</span>
          </div>

          {/* Document Metrics */}
          <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500">
            <span>
              {prescription.page_count} page{prescription.page_count === 1 ? '' : 's'}
            </span>
            <span>•</span>
            {avgConfidence !== null && (
              <>
                <span>{avgConfidence}% OCR conf</span>
                <span>•</span>
              </>
            )}
            <span>{totalChars.toLocaleString()} chars</span>
          </div>
        </div>
      )}

      {/* Right: Studio Action Bar */}
      <div className="flex items-center gap-2">
        {isUploaded && (
          <button
            disabled={isProcessing}
            onClick={onRunOCR}
            className="inline-flex items-center gap-1.5 rounded-xl bg-evergreen px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-ink disabled:opacity-50"
          >
            {isProcessing ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            <span>{isProcessing ? 'Processing…' : 'Run Extraction'}</span>
          </button>
        )}

        {dirtyCount > 0 && (
          <button
            onClick={onSaveCorrections}
            className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-blue-700 active:scale-95"
            title="Save pending corrections"
          >
            <Save size={14} />
            <span>Save Edits ({dirtyCount})</span>
          </button>
        )}

        {!isApproved && !isUploaded && (
          <button
            onClick={onConfirmAll}
            disabled={isProcessing}
            className="inline-flex items-center gap-1.5 rounded-xl border border-amber-300 bg-amber-50 px-3.5 py-2 text-xs font-semibold text-amber-900 shadow-sm transition hover:bg-amber-100 active:scale-95 disabled:opacity-50 cursor-pointer"
            title="Mark all fields as confirmed & verified"
          >
            <CheckSquare size={14} />
            <span>Confirm All{reviewRequiredFields.length > 0 ? ` (${reviewRequiredFields.length})` : ''}</span>
          </button>
        )}

        {!isApproved && !isUploaded && (
          <button
            onClick={onApprove}
            disabled={isProcessing}
            className="inline-flex items-center gap-1.5 rounded-xl bg-evergreen px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-ink active:scale-95 disabled:opacity-50 cursor-pointer"
            title="Approve and lock prescription version"
          >
            {isProcessing ? <Loader2 size={14} className="animate-spin" /> : <CheckCheck size={14} />}
            <span>{isProcessing ? 'Approving…' : 'Approve Version'}</span>
          </button>
        )}

        {isApproved && (
          <div className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-300 bg-emerald-50 px-3.5 py-2 text-xs font-bold text-emerald-900 shadow-sm">
            <ShieldCheck size={16} className="text-emerald-700" />
            <span>Approved & Locked</span>
          </div>
        )}

        <button
          onClick={onExport}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 hover:text-ink"
          title="Export structured JSON & evidence"
        >
          <Download size={14} />
          <span>Export JSON</span>
        </button>
      </div>
    </header>
  )
}
