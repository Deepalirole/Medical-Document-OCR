import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { api } from '../lib/api'
import type { FieldsResponse, PrescriptionField } from '../types'

export function MedicineTableView({
  prescriptionId,
  fieldsData,
  onChanged,
}: {
  prescriptionId: string
  fieldsData: FieldsResponse | null
  onChanged: () => void
}) {
  const [isAdding, setIsAdding] = useState(false)
  const [newMedicine, setNewMedicine] = useState({ medicine_name: '', strength: '', frequency: '' })

  const fields = fieldsData?.fields || []
  const medicineFields = fields.filter(
    (f) => f.field_path.startsWith('medicines[') && f.array_item_id,
  )

  // Group by array_item_id
  const rowsMap = medicineFields.reduce((acc, f) => {
    const itemId = f.array_item_id as string
    if (!acc.has(itemId)) acc.set(itemId, {})
    const key = f.field_path.split('.').pop() || ''
    acc.get(itemId)![key] = f
    return acc
  }, new Map<string, Record<string, PrescriptionField>>())

  async function handleAddRow() {
    if (!newMedicine.medicine_name.trim()) return
    setIsAdding(true)
    try {
      await api.mutateFields(prescriptionId, {
        add_items: [
          {
            array_path: 'medicines',
            values: {
              medicine_name: newMedicine.medicine_name,
              strength: newMedicine.strength || null,
              frequency: newMedicine.frequency || null,
            },
          },
        ],
      })
      setNewMedicine({ medicine_name: '', strength: '', frequency: '' })
      onChanged()
    } finally {
      setIsAdding(false)
    }
  }

  async function handleDeleteRow(itemId: string) {
    await api.mutateFields(prescriptionId, { remove_item_ids: [itemId] })
    onChanged()
  }

  async function handleUpdateCell(field: PrescriptionField, newValue: string) {
    if (field.current_value === newValue) return
    await api.correctField(prescriptionId, field.id, newValue, 'Table cell edit')
    onChanged()
  }

  return (
    <div className="flex h-full flex-col bg-white p-6">
      <div className="flex items-center justify-between border-b border-slate-200 pb-4">
        <div>
          <h2 className="text-lg font-bold text-ink">Prescribed Medicines & Remedies</h2>
          <p className="text-xs text-slate-500">
            Tabular structure mapped to schema with atomic evidence tracking.
          </p>
        </div>

        <span className="rounded-full bg-evergreen/10 px-3 py-1 font-mono text-xs font-bold text-evergreen">
          {rowsMap.size} item{rowsMap.size === 1 ? '' : 's'}
        </span>
      </div>

      {/* Main Table */}
      <div className="mt-4 flex-1 overflow-auto rounded-2xl border border-slate-200 shadow-sm">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-slate-200 bg-slate-50 font-bold uppercase tracking-wider text-slate-600">
            <tr>
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Medicine / Remedy Name</th>
              <th className="px-4 py-3">Strength / Potency</th>
              <th className="px-4 py-3">Frequency / Instructions</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-medium">
            {[...rowsMap.entries()].map(([itemId, rowFields], index) => {
              const nameField = rowFields['medicine_name']
              const strengthField = rowFields['strength']
              const freqField = rowFields['frequency']

              return (
                <tr key={itemId} className="hover:bg-slate-50/70 transition">
                  <td className="px-4 py-3 font-mono text-slate-400">{index + 1}</td>
                  <td className="px-4 py-2">
                    {nameField ? (
                      <input
                        type="text"
                        defaultValue={String(nameField.current_value || '')}
                        onBlur={(e) => void handleUpdateCell(nameField, e.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold focus:border-evergreen focus:outline-none"
                      />
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {strengthField ? (
                      <input
                        type="text"
                        defaultValue={String(strengthField.current_value || '')}
                        onBlur={(e) => void handleUpdateCell(strengthField, e.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                      />
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {freqField ? (
                      <input
                        type="text"
                        defaultValue={String(freqField.current_value || '')}
                        onBlur={(e) => void handleUpdateCell(freqField, e.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                      />
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => void handleDeleteRow(itemId)}
                      title="Remove row"
                      className="rounded-lg p-1.5 text-red-500 hover:bg-red-50 hover:text-red-700"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              )
            })}

            {/* Quick Add Row */}
            <tr className="bg-slate-50/40">
              <td className="px-4 py-3 font-mono text-evergreen">+</td>
              <td className="px-4 py-2">
                <input
                  type="text"
                  placeholder="New medicine name…"
                  value={newMedicine.medicine_name}
                  onChange={(e) => setNewMedicine((p) => ({ ...p, medicine_name: e.target.value }))}
                  className="w-full rounded-lg border border-dashed border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                />
              </td>
              <td className="px-4 py-2">
                <input
                  type="text"
                  placeholder="Strength (e.g. 30C, 500mg)…"
                  value={newMedicine.strength}
                  onChange={(e) => setNewMedicine((p) => ({ ...p, strength: e.target.value }))}
                  className="w-full rounded-lg border border-dashed border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                />
              </td>
              <td className="px-4 py-2">
                <input
                  type="text"
                  placeholder="Frequency (e.g. Once daily)…"
                  value={newMedicine.frequency}
                  onChange={(e) => setNewMedicine((p) => ({ ...p, frequency: e.target.value }))}
                  className="w-full rounded-lg border border-dashed border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                />
              </td>
              <td className="px-4 py-2 text-right">
                <button
                  disabled={!newMedicine.medicine_name.trim() || isAdding}
                  onClick={() => void handleAddRow()}
                  className="inline-flex items-center gap-1 rounded-lg bg-evergreen px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-ink disabled:opacity-30"
                >
                  <Plus size={13} />
                  <span>Add</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
