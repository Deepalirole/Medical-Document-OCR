import { Layers } from 'lucide-react'

import type { OCRResponse, PrescriptionDetail } from '../types'

export function PageStrip({
  prescription,
  ocr,
  currentPageIndex,
  onSelectPage,
}: {
  prescription: PrescriptionDetail | null
  ocr: OCRResponse | null
  currentPageIndex: number
  onSelectPage: (index: number) => void
}) {
  const pages = prescription?.pages || []
  if (pages.length === 0) return null

  // Map OCR confidence per page
  const ocrByPage = new Map<string, { confidence: number; textLen: number }>()
  if (ocr?.results) {
    for (const r of ocr.results) {
      ocrByPage.set(r.page_id, {
        confidence: Math.round((r.confidence || 0.9) * 100),
        textLen: r.raw_text?.length || 0,
      })
    }
  }

  return (
    <div className="border-b border-slate-200 bg-slate-50/70 px-6 py-3">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Layers size={14} className="text-evergreen" />
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Detected Pages & Sections ({pages.length})
          </span>
        </div>

        <span className="text-[11px] text-slate-400">
          Click any page to jump viewer and filter evidence
        </span>
      </div>

      <div className="mt-2.5 flex items-center gap-3 overflow-x-auto pb-1 scrollbar-thin">
        {pages.map((page, index) => {
          const isSelected = index === currentPageIndex
          const ocrInfo = ocrByPage.get(page.id) || { confidence: 90, textLen: 0 }
          const ops = page.preprocessing_applied || []

          return (
            <button
              key={page.id}
              onClick={() => onSelectPage(index)}
              className={`group flex min-w-44 items-center justify-between rounded-xl border p-2.5 text-left transition ${
                isSelected
                  ? 'border-evergreen bg-white shadow-sm ring-1 ring-evergreen'
                  : 'border-slate-200/80 bg-white hover:border-slate-300 hover:shadow-sm'
              }`}
            >
              <div className="truncate">
                <div className="flex items-center gap-1.5">
                  <span
                    className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold ${
                      isSelected ? 'bg-evergreen text-white' : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {page.page_number}
                  </span>
                  <p className="truncate text-xs font-bold text-ink">
                    Page {page.page_number}
                  </p>
                </div>
                <p className="mt-1 truncate text-[10px] text-slate-400">
                  {ops.length > 0 ? ops.join(', ') : 'standard render'}
                </p>
              </div>

              <div className="text-right">
                <span
                  className={`inline-flex items-center rounded-md px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                    ocrInfo.confidence >= 90
                      ? 'bg-emerald-50 text-emerald-700'
                      : ocrInfo.confidence >= 75
                        ? 'bg-amber-50 text-amber-700'
                        : 'bg-red-50 text-red-700'
                  }`}
                >
                  {ocrInfo.confidence}%
                </span>
                <p className="mt-0.5 text-[9px] font-mono text-slate-400">
                  {page.width}x{page.height}
                </p>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
