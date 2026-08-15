import { Check, Copy, Download, FileJson, X } from 'lucide-react'
import { useState } from 'react'

import type { FieldsResponse, PrescriptionDetail } from '../types'

export function ExportModal({
  prescription,
  fieldsData,
  onClose,
}: {
  prescription: PrescriptionDetail | null
  fieldsData: FieldsResponse | null
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)

  const jsonContent = JSON.stringify(fieldsData?.structured_json || {}, null, 2)

  function handleCopy() {
    void navigator.clipboard.writeText(jsonContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleDownload() {
    const filename = `${prescription?.original_filename || 'prescription'}_extracted.json`
    const blob = new Blob([jsonContent], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-3xl border border-slate-200 bg-white shadow-2xl">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-evergreen/10 text-evergreen">
              <FileJson size={20} />
            </div>
            <div>
              <h2 className="text-base font-bold text-ink">Export Structured JSON</h2>
              <p className="text-xs text-slate-500">
                {prescription?.original_filename || 'Prescription document'}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body: JSON Code */}
        <div className="flex-1 overflow-auto bg-slate-950 p-5 text-slate-200">
          <pre className="font-mono text-xs leading-5 select-all">{jsonContent}</pre>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-4">
          <span className="text-xs text-slate-500">
            {fieldsData?.fields.length || 0} fields mapped
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
            >
              {copied ? <Check size={14} className="text-evergreen" /> : <Copy size={14} />}
              <span>{copied ? 'Copied' : 'Copy JSON'}</span>
            </button>

            <button
              onClick={handleDownload}
              className="inline-flex items-center gap-1.5 rounded-xl bg-evergreen px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-ink active:scale-95"
            >
              <Download size={14} />
              <span>Download File</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
