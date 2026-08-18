import { useMemo, useRef, useState, type ChangeEvent } from 'react'
import { FileImage, FileText, UploadCloud, X } from 'lucide-react'

import { api } from '../lib/api'
import type { Prescription, PrescriptionSchema } from '../types'

interface Props {
  organizationId: string
  schemas: PrescriptionSchema[]
  onClose: () => void
  onCreated: (prescription: Prescription) => void
}

export function PrescriptionUploader({ organizationId, schemas, onClose, onCreated }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const activeSchemas = useMemo(
    () => schemas.filter((schema) => schema.organization_id === organizationId && schema.is_active),
    [organizationId, schemas],
  )
  const [schemaId, setSchemaId] = useState(activeSchemas[0]?.id || '')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setError('')
    setFile(event.target.files?.[0] || null)
  }

  async function upload() {
    if (!file || !schemaId) return
    setBusy(true)
    setError('')
    try {
      onCreated(await api.upload(organizationId, schemaId, file))
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Upload failed.')
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-ink/55 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="upload-title">
      <section className="w-full max-w-2xl rounded-3xl bg-white p-7 shadow-2xl">
        <div className="flex items-start justify-between">
          <div><p className="font-mono text-xs uppercase tracking-[0.2em] text-evergreen">Private ingestion</p><h2 id="upload-title" className="mt-2 text-2xl font-semibold">Add Medical Document / Bill</h2></div>
          <button aria-label="Close upload" className="rounded-lg p-2 hover:bg-slate-100" onClick={onClose}><X size={20} /></button>
        </div>
        <button type="button" onClick={() => input.current?.click()} className="mt-7 flex min-h-56 w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 px-6 text-center transition hover:border-evergreen hover:bg-mint/50">
          <span className="rounded-2xl bg-white p-4 text-evergreen shadow-sm"><UploadCloud size={28} /></span>
          {file ? <><span className="mt-4 font-semibold text-ink">{file.name}</span><span className="mt-1 text-sm text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB · ready for validation</span></> : <><span className="mt-4 font-semibold text-ink">Choose a Medical Bill, Prescription, or Receipt (PDF, JPG, PNG)</span><span className="mt-1 max-w-sm text-sm leading-6 text-slate-500">The original is preserved unchanged in private storage. Supports clinical prescriptions and itemized medical bills.</span></>}
        </button>
        <input ref={input} className="hidden" type="file" accept="application/pdf,image/jpeg,image/png" onChange={chooseFile} />
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">Extraction schema<select className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs" value={schemaId} onChange={(event) => setSchemaId(event.target.value)}><option value="">Select active schema</option>{activeSchemas.map((schema) => <option key={schema.id} value={schema.id}>{schema.name} · v{schema.version}</option>)}</select></label>
          <div className="rounded-xl bg-mint/70 p-4 text-sm text-evergreen"><div className="flex items-center gap-2 font-semibold">{file?.type === 'application/pdf' ? <FileText size={18} /> : <FileImage size={18} />} Evidence preserved</div><p className="mt-1 leading-5 text-evergreen/70">OCR and extracted fields stay visible with atomic evidence mapping.</p></div>
        </div>
        {activeSchemas.length === 0 && <p role="alert" className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">This organization needs an active schema before upload.</p>}
        {error && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <div className="mt-7 flex justify-end gap-3"><button className="rounded-xl px-5 py-3 font-semibold text-slate-600 hover:bg-slate-100" onClick={onClose}>Cancel</button><button disabled={!file || !schemaId || busy} className="rounded-xl bg-evergreen px-6 py-3 font-semibold text-white disabled:opacity-50" onClick={() => void upload()}>{busy ? 'Securing source…' : 'Upload document'}</button></div>
      </section>
    </div>
  )
}

