import { CheckCircle2, Plus, Trash2, X } from 'lucide-react'
import { useState } from 'react'

import { api } from '../lib/api'
import type { PrescriptionSchema } from '../types'

export function SchemaManager({ organizationId, schemas, onChanged, onClose }: { organizationId: string; schemas: PrescriptionSchema[]; onChanged: () => void; onClose: () => void }) {
  const [name, setName] = useState('')
  const [schemaKey, setSchemaKey] = useState('')
  const [definition, setDefinition] = useState('{\n  "schema_key": "",\n  "version": 1,\n  "sections": []\n}')
  const [error, setError] = useState('')
  const organizationSchemas = schemas.filter((schema) => schema.organization_id === organizationId)

  async function create() {
    setError('')
    try {
      const parsed = JSON.parse(definition) as Record<string, unknown>
      await api.createSchema({ organization_id: organizationId, schema_key: schemaKey, name, version: 1, definition: parsed })
      setName(''); setSchemaKey(''); onChanged()
    } catch (createError) { setError(createError instanceof Error ? createError.message : 'Schema could not be created.') }
  }

  return <div className="fixed inset-0 z-40 grid place-items-center bg-ink/55 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="schema-title"><section className="max-h-[92vh] w-full max-w-5xl overflow-auto rounded-3xl bg-white p-7 shadow-2xl"><header className="flex items-start justify-between"><div><p className="font-mono text-xs uppercase tracking-[0.2em] text-evergreen">Organization configuration</p><h2 id="schema-title" className="mt-2 text-2xl font-semibold">Dynamic schema registry</h2><p className="mt-1 text-sm text-slate-500">Active versions are immutable; editing one creates a new draft version.</p></div><button aria-label="Close schemas" className="rounded-lg p-2 hover:bg-slate-100" onClick={onClose}><X /></button></header><div className="mt-7 grid gap-6 lg:grid-cols-[0.9fr_1.1fr]"><div><h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">Versions</h3><div className="mt-3 space-y-3">{organizationSchemas.map((schema) => <article key={schema.id} className="rounded-xl border border-slate-200 p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-semibold">{schema.name}</p><p className="mt-1 font-mono text-xs text-slate-500">{schema.schema_key} · v{schema.version}</p></div>{schema.is_active ? <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-2 py-1 text-xs text-evergreen"><CheckCircle2 size={13} /> Active</span> : <div className="flex gap-1"><button className="rounded-lg px-2 py-1 text-xs font-semibold text-evergreen hover:bg-mint" onClick={() => void api.activateSchema(schema.id).then(onChanged)}>Activate</button><button aria-label={`Delete ${schema.name}`} className="rounded-lg p-2 text-red-600 hover:bg-red-50" onClick={() => void api.deleteSchema(schema.id).then(onChanged)}><Trash2 size={15} /></button></div>}</div></article>)}{organizationSchemas.length === 0 && <p className="rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-500">No schema versions yet.</p>}</div></div><div className="rounded-2xl bg-slate-50 p-5"><h3 className="font-semibold">Create draft</h3><div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="text-sm font-medium">Name<input className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2" value={name} onChange={(event) => setName(event.target.value)} /></label><label className="text-sm font-medium">Schema key<input className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono" placeholder="general_opd" value={schemaKey} onChange={(event) => setSchemaKey(event.target.value)} /></label></div><label className="mt-4 block text-sm font-medium">Definition JSON<textarea className="mt-2 min-h-80 w-full rounded-xl border border-slate-200 bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-100" value={definition} onChange={(event) => setDefinition(event.target.value)} /></label>{error && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}<button disabled={!name || !schemaKey} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-evergreen px-5 py-3 font-semibold text-white disabled:opacity-40" onClick={() => void create()}><Plus size={17} /> Create draft</button></div></div></section></div>
}

