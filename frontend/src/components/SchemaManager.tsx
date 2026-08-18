import { CheckCircle2, FileSpreadsheet, FileText, Plus, Sparkles, Trash2, X } from 'lucide-react'
import { useState } from 'react'

import { api } from '../lib/api'
import type { PrescriptionSchema } from '../types'

const TEMPLATES = {
  general_opd: {
    name: 'General OPD Prescription',
    schemaKey: 'general_opd',
    definition: {
      schema_key: 'general_opd',
      version: 1,
      sections: [
        {
          key: 'patient',
          type: 'object',
          label: 'Patient Information',
          fields: [
            { key: 'name', type: 'string', required: true, aliases: ['patient name', 'patient', 'name'] },
            { key: 'age', type: 'string', required: false, aliases: ['age', 'yrs'] },
            { key: 'gender', type: 'string', required: false, aliases: ['gender', 'sex'] },
          ],
        },
        {
          key: 'clinician',
          type: 'object',
          label: 'Treating Clinician',
          fields: [
            { key: 'doctor_name', type: 'string', required: false, aliases: ['doctor', 'dr', 'physician', 'consultant'] },
            { key: 'specialty', type: 'string', required: false, aliases: ['specialty', 'department', 'designation'] },
          ],
        },
        {
          key: 'medicines',
          type: 'medicine_list',
          label: 'Prescribed Medicines',
          required: true,
          aliases: ['medicines', 'prescribed remedies', 'rx', 'drugs', 'treatment'],
          item_schema: {
            medicine_name: { type: 'string', required: true, aliases: ['medicine', 'drug name', 'remedy'] },
            strength: { type: 'string', aliases: ['strength', 'dosage', 'potency', 'mg'] },
            frequency: { type: 'string', aliases: ['frequency', 'timing', 'daily', 'instructions'] },
            duration: { type: 'string', aliases: ['duration', 'days', 'period'] },
          },
        },
        {
          key: 'diagnosis',
          type: 'object',
          label: 'Clinical Diagnosis & Advice',
          fields: [
            { key: 'clinical_impression', type: 'string', required: false, aliases: ['diagnosis', 'impression', 'complaint'] },
            { key: 'advice', type: 'string', required: false, aliases: ['advice', 'instructions', 'precautions'] },
            { key: 'follow_up', type: 'string', required: false, aliases: ['follow up', 'next visit', 'review on'] },
          ],
        },
      ],
    },
  },
  medical_bill: {
    name: 'Medical Bill & Pharmacy Receipt',
    schemaKey: 'medical_bill',
    definition: {
      schema_key: 'medical_bill',
      version: 1,
      sections: [
        {
          key: 'provider',
          type: 'object',
          label: 'Hospital & Pharmacy Details',
          fields: [
            { key: 'hospital_name', type: 'string', required: false, aliases: ['hospital', 'pharmacy', 'clinic', 'chemist', 'center', 'store', 'medical store'] },
            { key: 'doctor_name', type: 'string', required: false, aliases: ['doctor', 'consultant', 'dr', 'prescriber', 'physician'] },
            { key: 'bill_number', type: 'string', required: false, aliases: ['invoice', 'bill no', 'receipt no', 'cash memo', 'invoice no', 'bill number', 'receipt'] },
            { key: 'bill_date', type: 'string', required: false, aliases: ['date', 'receipt date', 'invoice date', 'bill date', 'billing date', 'dated'] },
            { key: 'tax_id', type: 'string', required: false, aliases: ['gstin', 'gst', 'tin', 'dl no', 'license no', 'drug license'] },
            { key: 'contact_number', type: 'string', required: false, aliases: ['phone', 'mobile', 'tel', 'contact', 'ph'] },
          ],
        },
        {
          key: 'patient',
          type: 'object',
          label: 'Patient & Customer Details',
          fields: [
            { key: 'name', type: 'string', required: true, aliases: ['patient name', 'patient', 'customer', 'client', 'm/s', 'mr', 'mrs'] },
            { key: 'patient_id', type: 'string', required: false, aliases: ['uhid', 'patient id', 'ipd no', 'opd no', 'mrn', 'reg no'] },
            { key: 'age', type: 'string', required: false, aliases: ['age', 'yrs', 'years'] },
            { key: 'gender', type: 'string', required: false, aliases: ['gender', 'sex', 'male', 'female'] },
          ],
        },
        {
          key: 'medicines',
          type: 'medicine_list',
          label: 'Billed Medicines & Items',
          required: true,
          aliases: ['items', 'medicines', 'drugs', 'products', 'particulars', 'description', 'billed items'],
          item_schema: {
            medicine_name: { type: 'string', required: true, aliases: ['medicine', 'item', 'product', 'drug', 'description', 'item name'] },
            unique_code: { type: 'string', aliases: ['unique code', 'batch', 'batch no', 'hsn', 'hsn code', 'item code', 'barcode'] },
            unit_price: { type: 'number', aliases: ['cost', 'unit price', 'price', 'rate', 'mrp', 'unit cost'] },
            quantity: { type: 'number', aliases: ['qty', 'quantity', 'units', 'count', 'packs'] },
            discount: { type: 'number', aliases: ['discount', 'disc', 'disc %', 'less'] },
            tax_rate: { type: 'number', aliases: ['tax', 'gst', 'vat', 'cgst', 'sgst'] },
            total_price: { type: 'number', aliases: ['amount', 'total', 'net amount', 'item total', 'line total', 'price'] },
          },
        },
        {
          key: 'billing_summary',
          type: 'object',
          label: 'Financial Summary & Totals',
          fields: [
            { key: 'subtotal', type: 'number', required: false, aliases: ['subtotal', 'sub total', 'taxable amount', 'gross total', 'gross amount'] },
            { key: 'discount_total', type: 'number', required: false, aliases: ['discount total', 'total discount', 'discount'] },
            { key: 'tax_amount', type: 'number', required: false, aliases: ['tax amount', 'total tax', 'gst total', 'cgst + sgst', 'vat total'] },
            { key: 'total_cost', type: 'number', required: true, aliases: ['total cost', 'grand total', 'net amount', 'total amount', 'net payable', 'amount payable', 'total'] },
            { key: 'payment_mode', type: 'string', required: false, aliases: ['payment mode', 'mode', 'cash', 'card', 'upi', 'online', 'credit'] },
            { key: 'payment_status', type: 'string', required: false, aliases: ['payment status', 'paid', 'due', 'pending', 'settled'] },
          ],
        },
      ],
    },
  },
}

export function SchemaManager({
  organizationId,
  schemas,
  onChanged,
  onClose,
}: {
  organizationId: string
  schemas: PrescriptionSchema[]
  onChanged: () => void
  onClose: () => void
}) {
  const [name, setName] = useState('')
  const [schemaKey, setSchemaKey] = useState('')
  const [definition, setDefinition] = useState('{\n  "schema_key": "",\n  "version": 1,\n  "sections": []\n}')
  const [error, setError] = useState('')
  const organizationSchemas = schemas.filter((schema) => schema.organization_id === organizationId)

  function loadTemplate(key: keyof typeof TEMPLATES) {
    const template = TEMPLATES[key]
    setName(template.name)
    setSchemaKey(template.schemaKey)
    setDefinition(JSON.stringify(template.definition, null, 2))
    setError('')
  }

  async function create() {
    setError('')
    try {
      const parsed = JSON.parse(definition) as Record<string, unknown>
      await api.createSchema({
        organization_id: organizationId,
        schema_key: schemaKey,
        name,
        version: 1,
        definition: parsed,
      })
      setName('')
      setSchemaKey('')
      onChanged()
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : 'Schema could not be created.')
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-ink/55 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="schema-title"
    >
      <section className="max-h-[92vh] w-full max-w-5xl overflow-auto rounded-3xl bg-white p-7 shadow-2xl">
        <header className="flex items-start justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-evergreen">
              Organization configuration
            </p>
            <h2 id="schema-title" className="mt-2 text-2xl font-semibold">
              Dynamic Document & Bill Schema Registry
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Manage schema definitions for clinical prescriptions, medical bills, and pharmacy receipts.
            </p>
          </div>
          <button aria-label="Close schemas" className="rounded-lg p-2 hover:bg-slate-100" onClick={onClose}>
            <X />
          </button>
        </header>

        <div className="mt-7 grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          {/* Left Column: Registered Versions */}
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">Active Versions</h3>
            <div className="mt-3 space-y-3">
              {organizationSchemas.map((schema) => (
                <article key={schema.id} className="rounded-xl border border-slate-200 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-sm">{schema.name}</p>
                      <p className="mt-1 font-mono text-xs text-slate-500">
                        {schema.schema_key} · v{schema.version}
                      </p>
                    </div>
                    {schema.is_active ? (
                      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-2 py-1 text-xs font-semibold text-evergreen">
                        <CheckCircle2 size={13} /> Active
                      </span>
                    ) : (
                      <div className="flex items-center gap-1">
                        <button
                          className="rounded-lg px-2.5 py-1 text-xs font-semibold text-evergreen hover:bg-mint"
                          onClick={() => void api.activateSchema(schema.id).then(onChanged)}
                        >
                          Activate
                        </button>
                        <button
                          aria-label={`Delete ${schema.name}`}
                          className="rounded-lg p-2 text-red-600 hover:bg-red-50"
                          onClick={() => void api.deleteSchema(schema.id).then(onChanged)}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    )}
                  </div>
                </article>
              ))}
              {organizationSchemas.length === 0 && (
                <p className="rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-500">
                  No schema versions yet. Use the quick templates below to create one.
                </p>
              )}
            </div>
          </div>

          {/* Right Column: Create Draft Schema with Templates */}
          <div className="rounded-2xl bg-slate-50 p-5">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Create draft schema</h3>
              <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium">
                <Sparkles size={14} className="text-amber-500" />
                <span>Templates:</span>
              </div>
            </div>

            {/* Quick Template Buttons */}
            <div className="mt-2.5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => loadTemplate('medical_bill')}
                className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-100 transition shadow-2xs"
              >
                <FileSpreadsheet size={14} className="text-emerald-700" />
                <span>Medical Bill & Pharmacy Receipt</span>
              </button>

              <button
                type="button"
                onClick={() => loadTemplate('general_opd')}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition shadow-2xs"
              >
                <FileText size={14} className="text-slate-600" />
                <span>General OPD Prescription</span>
              </button>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="text-sm font-medium">
                Name
                <input
                  className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs"
                  placeholder="Medical Bill & Pharmacy Receipt"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label className="text-sm font-medium">
                Schema key
                <input
                  className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs"
                  placeholder="medical_bill"
                  value={schemaKey}
                  onChange={(event) => setSchemaKey(event.target.value)}
                />
              </label>
            </div>

            <label className="mt-4 block text-sm font-medium">
              Definition JSON
              <textarea
                className="mt-2 min-h-72 w-full rounded-xl border border-slate-200 bg-slate-950 p-4 font-mono text-xs leading-5 text-slate-100"
                value={definition}
                onChange={(event) => setDefinition(event.target.value)}
              />
            </label>

            {error && (
              <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                {error}
              </p>
            )}

            <button
              disabled={!name || !schemaKey}
              className="mt-4 inline-flex items-center gap-2 rounded-xl bg-evergreen px-5 py-3 font-semibold text-white disabled:opacity-40 hover:bg-ink transition shadow-sm"
              onClick={() => void create()}
            >
              <Plus size={17} /> Create draft
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
