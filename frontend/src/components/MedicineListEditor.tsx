import { Plus, Trash2 } from 'lucide-react'

import { api } from '../lib/api'
import type { PrescriptionField } from '../types'
import { FieldEditor } from './FieldEditor'

interface Node { key: string; type: string; item_schema: Record<string, { type: string; required?: boolean }> }

export function MedicineListEditor({ prescriptionId, node, fields, onChanged }: { prescriptionId: string; node: Node; fields: PrescriptionField[]; onChanged: () => void }) {
  const relevant = fields.filter((field) => field.field_path.startsWith(`${node.key}[`) && field.array_item_id)
  const rows = relevant.reduce((grouped, field) => {
    const itemId = field.array_item_id as string
    grouped.set(itemId, [...(grouped.get(itemId) || []), field])
    return grouped
  }, new Map<string, PrescriptionField[]>())

  async function add() {
    const values = Object.fromEntries(Object.keys(node.item_schema).map((key) => [key, null]))
    await api.mutateFields(prescriptionId, { add_items: [{ array_path: node.key, values }] })
    onChanged()
  }

  async function remove(itemId: string) {
    await api.mutateFields(prescriptionId, { remove_item_ids: [itemId] })
    onChanged()
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
      <div className="flex items-center justify-between"><div><h3 className="font-semibold capitalize">{node.key.replaceAll('_', ' ')}</h3><p className="text-xs text-slate-500">Repeatable, evidence-linked rows</p></div><button className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-evergreen shadow-sm" onClick={() => void add()}><Plus size={14} /> Add row</button></div>
      <div className="mt-4 space-y-4">{[...rows.entries()].map(([itemId, rowFields], index) => {
        const removed = rowFields.every((field) => field.current_value === null)
        if (removed) return null
        return <article key={itemId} className="rounded-xl border border-slate-200 bg-white p-4"><div className="mb-3 flex items-center justify-between"><p className="font-mono text-xs uppercase tracking-wider text-slate-500">Row {index + 1}</p><button aria-label={`Remove row ${index + 1}`} className="rounded-lg p-2 text-red-600 hover:bg-red-50" onClick={() => void remove(itemId)}><Trash2 size={16} /></button></div><div className="grid gap-3 sm:grid-cols-2">{rowFields.map((field) => <FieldEditor key={field.id} prescriptionId={prescriptionId} field={field} label={field.field_path.split('.').at(-1) || field.field_path} onSaved={onChanged} />)}</div></article>
      })}{rows.size === 0 && <p className="rounded-xl border border-dashed border-slate-300 p-5 text-center text-sm text-slate-500">No rows extracted. Add one during review if the source supports it.</p>}</div>
    </section>
  )
}
