import {
  ChevronLeft,
  ChevronRight,
  ImageIcon,
  RotateCcw,
  RotateCw,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { useState } from 'react'

import type { PrescriptionDetail } from '../types'

export function PrescriptionViewer({
  prescription,
  pageIndex: controlledPageIndex,
  onPageChange,
}: {
  prescription: PrescriptionDetail | null
  pageIndex?: number
  onPageChange?: (index: number) => void
}) {
  const [internalPageIndex, setInternalPageIndex] = useState(0)
  const [rotation, setRotation] = useState(0)
  const [zoom, setZoom] = useState(1)

  const pages = prescription?.pages || []
  const pageIndex = controlledPageIndex !== undefined ? controlledPageIndex : internalPageIndex
  const setPageIndex = (idx: number | ((prev: number) => number)) => {
    const nextIdx = typeof idx === 'function' ? idx(pageIndex) : idx
    if (onPageChange) onPageChange(nextIdx)
    else setInternalPageIndex(nextIdx)
  }

  const page = pages[pageIndex]

  const handleRotateCw = () => setRotation((prev) => (prev + 90) % 360)
  const handleRotateCcw = () => setRotation((prev) => (prev - 90 + 360) % 360)
  const handleZoomIn = () => setZoom((prev) => Math.min(prev + 0.25, 3))
  const handleZoomOut = () => setZoom((prev) => Math.max(prev - 0.25, 0.5))
  const handleFit = () => {
    setZoom(1)
    setRotation(0)
  }

  if (!page) {
    return (
      <div className="grid min-h-[520px] place-items-center rounded-2xl bg-slate-50 text-sm text-slate-500">
        <div className="text-center">
          <ImageIcon className="mx-auto mb-3 text-slate-300" size={32} />
          <p className="font-semibold text-slate-600">Document Canvas</p>
          <p className="text-xs text-slate-400">Page preview appears after rendering.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Viewer Header Toolbar matching reference */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-3 bg-slate-50/50">
        {/* Left: Page Navigator */}
        <div className="flex items-center gap-1.5">
          <button
            aria-label="Previous page"
            disabled={pageIndex === 0}
            className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-30 shadow-sm"
            onClick={() => setPageIndex((v) => Math.max(0, v - 1))}
            title="Previous page"
          >
            <ChevronLeft size={16} />
          </button>

          <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-700 shadow-sm">
            <span>PDF page</span>
            <span className="font-mono text-evergreen">
              {page.page_number} / {pages.length}
            </span>
          </div>

          <button
            aria-label="Next page"
            disabled={pageIndex === pages.length - 1}
            className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-30 shadow-sm"
            onClick={() => setPageIndex((v) => Math.min(pages.length - 1, v + 1))}
            title="Next page"
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {/* Center: Zoom & Fit Tools */}
        <div className="flex items-center gap-1.5">
          <div className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5 shadow-sm">
            <button
              aria-label="Zoom out"
              className="rounded p-1 text-slate-600 hover:bg-slate-100 disabled:opacity-30"
              disabled={zoom <= 0.5}
              onClick={handleZoomOut}
              title="Zoom out"
            >
              <ZoomOut size={15} />
            </button>
            <button
              onClick={handleFit}
              className="px-2 py-0.5 font-mono text-[11px] font-bold text-slate-600 hover:bg-slate-100 rounded"
              title="Reset fit"
            >
              fit · {Math.round(zoom * 100)}%
            </button>
            <button
              aria-label="Zoom in"
              className="rounded p-1 text-slate-600 hover:bg-slate-100 disabled:opacity-30"
              disabled={zoom >= 3}
              onClick={handleZoomIn}
              title="Zoom in"
            >
              <ZoomIn size={15} />
            </button>
          </div>

          {/* Rotate Tools */}
          <div className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5 shadow-sm">
            <button
              aria-label="Rotate counter-clockwise"
              className="rounded p-1 text-slate-600 hover:bg-slate-100"
              onClick={handleRotateCcw}
              title="Rotate left"
            >
              <RotateCcw size={15} />
            </button>
            <button
              aria-label="Rotate clockwise"
              className="rounded p-1 text-slate-600 hover:bg-slate-100"
              onClick={handleRotateCw}
              title="Rotate right"
            >
              <RotateCw size={15} />
            </button>
          </div>
        </div>

        {/* Right: Language / OCR Stats Tag */}
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-lg border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] font-semibold text-slate-600 shadow-sm">
            en · 90% conf
          </span>
        </div>
      </div>

      {/* Main Image Canvas */}
      <div className="relative flex-1 overflow-auto bg-slate-900/5 p-6 flex items-center justify-center min-h-[560px]">
        {page.preview_url ? (
          <div
            className="transition-transform duration-200 ease-out"
            style={{
              transform: `rotate(${rotation}deg) scale(${zoom})`,
              transformOrigin: 'center center',
            }}
          >
            <img
              className="max-h-[750px] w-auto max-w-full rounded-xl bg-white object-contain shadow-2xl ring-1 ring-slate-900/10"
              src={page.preview_url}
              alt={`Prescription page ${page.page_number}`}
            />
          </div>
        ) : (
          <div className="text-center text-sm text-slate-400">
            <p>Preview loading…</p>
          </div>
        )}
      </div>
    </div>
  )
}

