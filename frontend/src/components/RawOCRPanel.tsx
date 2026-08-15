import { Check, Copy, Database, ScanText, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { OCRResponse } from '../types'

export function RawOCRPanel({ ocr }: { ocr: OCRResponse | null }) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedPage, setSelectedPage] = useState<number | 'ALL'>('ALL')
  const [copiedPageId, setCopiedPageId] = useState<string | null>(null)

  const results = useMemo(() => ocr?.results || [], [ocr?.results])

  const filteredResults = useMemo(() => {
    return results.filter((res, idx) => {
      if (selectedPage !== 'ALL' && idx !== selectedPage) return false
      if (searchQuery.trim()) {
        const text = res.raw_text?.toLowerCase() || ''
        if (!text.includes(searchQuery.toLowerCase())) return false
      }
      return true
    })
  }, [results, selectedPage, searchQuery])

  function handleCopy(pageId: string, text: string) {
    void navigator.clipboard.writeText(text)
    setCopiedPageId(pageId)
    setTimeout(() => setCopiedPageId(null), 2000)
  }

  if (!results.length) {
    return (
      <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
        <div>
          <Database size={32} className="mx-auto mb-2 text-slate-300" />
          <p className="font-semibold text-slate-600">Raw OCR Layer</p>
          <p className="text-xs text-slate-400">No OCR text tokens have been persisted yet.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-white p-6">
      {/* Header & Filter Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4">
        <div>
          <h2 className="text-lg font-bold text-ink">Canonical OCR Evidence</h2>
          <p className="text-xs text-slate-500">
            Immutable Tesseract engine output preserved for audit and verification.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {/* Search */}
          <div className="relative min-w-44">
            <Search className="absolute left-2.5 top-2 text-slate-400" size={13} />
            <input
              type="text"
              placeholder="Search OCR text…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-1.5 pl-8 pr-3 text-xs focus:border-evergreen focus:bg-white focus:outline-none"
            />
          </div>

          {/* Page Filter */}
          <select
            aria-label="Filter OCR by page"
            value={selectedPage}
            onChange={(e) =>
              setSelectedPage(e.target.value === 'ALL' ? 'ALL' : Number(e.target.value))
            }
            className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm focus:outline-none cursor-pointer"
          >
            <option value="ALL">All pages ({results.length})</option>
            {results.map((_, i) => (
              <option key={i} value={i}>
                Page {i + 1}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* OCR Results Stream */}
      <div className="mt-4 flex-1 overflow-y-auto space-y-4">
        {filteredResults.map((result, index) => {
          const charCount = result.raw_text?.length || 0

          return (
            <article
              key={result.id}
              className="rounded-2xl border border-slate-200 bg-slate-50/40 p-4 shadow-sm"
            >
              <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/70 pb-3">
                <div className="flex items-center gap-2">
                  <ScanText className="text-evergreen" size={16} />
                  <span className="text-xs font-bold text-ink">
                    Page {index + 1} · Text Stream
                  </span>
                  <span className="font-mono text-[10px] text-slate-400">
                    ({charCount.toLocaleString()} chars)
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-600">
                    {result.provider}
                  </span>
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-600">
                    {result.processing_ms} ms
                  </span>
                  {result.confidence !== null && (
                    <span className="rounded-md bg-emerald-50 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-700">
                      {Math.round(result.confidence * 100)}%
                    </span>
                  )}

                  <button
                    onClick={() => handleCopy(result.id, result.raw_text || '')}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 shadow-sm hover:bg-slate-50"
                  >
                    {copiedPageId === result.id ? (
                      <Check size={12} className="text-evergreen" />
                    ) : (
                      <Copy size={12} />
                    )}
                    <span>{copiedPageId === result.id ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>
              </header>

              <pre className="mt-3 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-xl bg-white p-4 font-mono text-xs leading-6 text-slate-700 border border-slate-200/80 shadow-inner">
                {result.raw_text || 'No text detected on this page.'}
              </pre>
            </article>
          )
        })}

        {filteredResults.length === 0 && (
          <p className="py-8 text-center text-xs text-slate-400">
            No OCR text matching your search query.
          </p>
        )}
      </div>
    </div>
  )
}


