import { DollarSign, Plus, Trash2 } from 'lucide-react'
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
  const [newMedicine, setNewMedicine] = useState({
    medicine_name: '',
    unique_code: '',
    unit_price: '',
    quantity: '1',
    total_price: '',
    strength: '',
    frequency: '',
  })

  const fields = fieldsData?.fields || []
  const medicineFields = fields.filter(
    (f) => f.field_path.startsWith('medicines[') && f.array_item_id,
  )

  // Determine if this document is a Medical Bill with pricing/batch columns
  const hasBillingColumns = fields.some(
    (f) =>
      f.field_path.includes('.unit_price') ||
      f.field_path.includes('.total_price') ||
      f.field_path.includes('.unique_code') ||
      f.field_path.includes('billing_summary'),
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
      const values: Record<string, unknown> = {
        medicine_name: newMedicine.medicine_name,
      }

      if (hasBillingColumns) {
        if (newMedicine.unique_code) values.unique_code = newMedicine.unique_code
        if (newMedicine.unit_price) values.unit_price = Number(newMedicine.unit_price) || newMedicine.unit_price
        if (newMedicine.quantity) values.quantity = Number(newMedicine.quantity) || newMedicine.quantity
        const unit = Number(newMedicine.unit_price)
        const qty = Number(newMedicine.quantity) || 1
        const total = newMedicine.total_price ? Number(newMedicine.total_price) : (!isNaN(unit) ? unit * qty : null)
        if (total !== null) values.total_price = total
      } else {
        if (newMedicine.strength) values.strength = newMedicine.strength
        if (newMedicine.frequency) values.frequency = newMedicine.frequency
      }

      await api.mutateFields(prescriptionId, {
        add_items: [
          {
            array_path: 'medicines',
            values,
          },
        ],
      })
      setNewMedicine({
        medicine_name: '',
        unique_code: '',
        unit_price: '',
        quantity: '1',
        total_price: '',
        strength: '',
        frequency: '',
      })
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
    const parsed = (field.field_type === 'number' && !isNaN(Number(newValue))) ? Number(newValue) : newValue
    await api.correctField(prescriptionId, field.id, parsed, 'Table cell edit')
    onChanged()
  }

  return (
    <div className="flex h-full flex-col bg-white p-6">
      <div className="flex items-center justify-between border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-ink">
              {hasBillingColumns ? 'Billed Medicines & Medical Items' : 'Prescribed Medicines & Remedies'}
            </h2>
            {hasBillingColumns && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-bold text-emerald-800">
                <DollarSign size={12} /> Medical Bill
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500">
            {hasBillingColumns
              ? 'Itemized medicines, batch/code, unit rate, quantity, and amount mapped to evidence.'
              : 'Tabular clinical prescription structure mapped to schema with atomic evidence tracking.'}
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
            {hasBillingColumns ? (
              <tr>
                <th className="px-4 py-3">#</th>
                <th className="px-4 py-3">Medicine / Item Name</th>
                <th className="px-4 py-3">Unique Code / Batch</th>
                <th className="px-4 py-3 text-right">Unit Price (₹)</th>
                <th className="px-4 py-3 text-center">Qty</th>
                <th className="px-4 py-3 text-right">Total Amount (₹)</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            ) : (
              <tr>
                <th className="px-4 py-3">#</th>
                <th className="px-4 py-3">Medicine / Remedy Name</th>
                <th className="px-4 py-3">Strength / Potency</th>
                <th className="px-4 py-3">Frequency / Instructions</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            )}
          </thead>
          <tbody className="divide-y divide-slate-100 font-medium">
            {[...rowsMap.entries()].map(([itemId, rowFields], index) => {
              const nameField = rowFields['medicine_name'] || rowFields['item_name']
              const uniqueCodeField = rowFields['unique_code'] || rowFields['batch_no']
              const unitPriceField = rowFields['unit_price'] || rowFields['price'] || rowFields['mrp']
              const qtyField = rowFields['quantity'] || rowFields['qty']
              const totalField = rowFields['total_price'] || rowFields['amount']
              const strengthField = rowFields['strength']
              const freqField = rowFields['frequency']

              if (hasBillingColumns) {
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
                      {uniqueCodeField ? (
                        <input
                          type="text"
                          defaultValue={String(uniqueCodeField.current_value || '')}
                          onBlur={(e) => void handleUpdateCell(uniqueCodeField, e.target.value)}
                          className="w-full font-mono text-xs rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 focus:border-evergreen focus:outline-none"
                        />
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {unitPriceField ? (
                        <input
                          type="text"
                          defaultValue={String(unitPriceField.current_value || '')}
                          onBlur={(e) => void handleUpdateCell(unitPriceField, e.target.value)}
                          className="w-24 text-right font-mono rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                        />
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {qtyField ? (
                        <input
                          type="text"
                          defaultValue={String(qtyField.current_value || '')}
                          onBlur={(e) => void handleUpdateCell(qtyField, e.target.value)}
                          className="w-16 text-center font-mono rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                        />
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {totalField ? (
                        <input
                          type="text"
                          defaultValue={String(totalField.current_value || '')}
                          onBlur={(e) => void handleUpdateCell(totalField, e.target.value)}
                          className="w-24 text-right font-mono font-bold rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
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
              }

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
                  placeholder="New medicine / item name…"
                  value={newMedicine.medicine_name}
                  onChange={(e) => setNewMedicine((p) => ({ ...p, medicine_name: e.target.value }))}
                  className="w-full rounded-lg border border-dashed border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                />
              </td>

              {hasBillingColumns ? (
                <>
                  <td className="px-4 py-2">
                    <input
                      type="text"
                      placeholder="Batch / Code…"
                      value={newMedicine.unique_code}
                      onChange={(e) => setNewMedicine((p) => ({ ...p, unique_code: e.target.value }))}
                      className="w-full font-mono text-xs rounded-lg border border-dashed border-slate-300 bg-white px-2.5 py-1.5 focus:border-evergreen focus:outline-none"
                    />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <input
                      type="text"
                      placeholder="Unit rate…"
                      value={newMedicine.unit_price}
                      onChange={(e) => setNewMedicine((p) => ({ ...p, unit_price: e.target.value }))}
                      className="w-24 text-right font-mono rounded-lg border border-dashed border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                    />
                  </td>
                  <td className="px-4 py-2 text-center">
                    <input
                      type="text"
                      placeholder="Qty…"
                      value={newMedicine.quantity}
                      onChange={(e) => setNewMedicine((p) => ({ ...p, quantity: e.target.value }))}
                      className="w-16 text-center font-mono rounded-lg border border-dashed border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                    />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <input
                      type="text"
                      placeholder="Total…"
                      value={newMedicine.total_price}
                      onChange={(e) => setNewMedicine((p) => ({ ...p, total_price: e.target.value }))}
                      className="w-24 text-right font-mono font-bold rounded-lg border border-dashed border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-evergreen focus:outline-none"
                    />
                  </td>
                </>
              ) : (
                <>
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
                </>
              )}

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
