import { Check, Copy, Download, FileJson, FileSpreadsheet, Layers, Table } from 'lucide-react'
import { useState } from 'react'

import { api } from '../lib/api'
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
  const [activeFormat, setActiveFormat] = useState<'json' | 'excel'>('excel')
  const [copied, setCopied] = useState(false)
  const [downloading, setDownloading] = useState(false)

  const structured = fieldsData?.structured_json || {}
  const jsonContent = JSON.stringify(structured, null, 2)

  // Extract common sections for preview & CSV generation
  const provider = (structured.provider || structured.clinician || {}) as Record<string, unknown>
  const patient = (structured.patient || {}) as Record<string, unknown>
  const billingSummary = (structured.billing_summary || {}) as Record<string, unknown>
  const rawMedicines = (structured.medicines || structured.items || []) as Array<Record<string, unknown>>
  const medicines = Array.isArray(rawMedicines) ? rawMedicines : []

  function handleCopy() {
    void navigator.clipboard.writeText(jsonContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleDownloadJson() {
    const rawName = prescription?.original_filename || 'medical_document'
    const baseName = rawName.replace(/\.[^/.]+$/, '')
    const filename = `${baseName}_extracted.json`
    const blob = new Blob([jsonContent], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  async function handleDownloadExcel() {
    if (!prescription) return
    setDownloading(true)
    try {
      const blob = await api.exportExcelBlob(prescription.id)
      const rawName = prescription.original_filename || 'medical_document'
      const baseName = rawName.replace(/\.[^/.]+$/, '')
      const filename = `${baseName}_export.xlsx`
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      // Fallback: generate formatted CSV
      handleDownloadCsv()
    } finally {
      setDownloading(false)
    }
  }

  function handleDownloadCsv() {
    const rawName = prescription?.original_filename || 'medical_document'
    const baseName = rawName.replace(/\.[^/.]+$/, '')
    const filename = `${baseName}_export.csv`

    const csvRows: string[] = []
    csvRows.push(`"MEDICAL DOCUMENT & BILL EXTRACTION REPORT"`)
    csvRows.push(`"Document Filename:","${prescription?.original_filename || ''}"`)
    csvRows.push(`"Document ID:","${prescription?.id || ''}"`)
    csvRows.push('')

    // Provider details
    csvRows.push(`"--- 1. PROVIDER & CLINICIAN DETAILS ---"`)
    csvRows.push(`"Hospital / Pharmacy:","${String(provider.hospital_name || provider.name || '—')}"`)
    csvRows.push(`"Doctor / Clinician:","${String(provider.doctor_name || provider.doctor || '—')}"`)
    csvRows.push(`"Bill / Invoice No:","${String(provider.bill_number || provider.invoice_no || '—')}"`)
    csvRows.push(`"Receipt Date:","${String(provider.bill_date || provider.date || '—')}"`)
    csvRows.push(`"Tax / GSTIN ID:","${String(provider.tax_id || provider.gstin || '—')}"`)
    csvRows.push(`"Contact Number:","${String(provider.contact_number || provider.phone || '—')}"`)
    csvRows.push('')

    // Patient details
    csvRows.push(`"--- 2. PATIENT INFORMATION ---"`)
    csvRows.push(`"Patient Name:","${String(patient.name || patient.patient_name || '—')}"`)
    csvRows.push(`"Patient ID / UHID:","${String(patient.patient_id || patient.uhid || '—')}"`)
    csvRows.push(`"Age / Gender:","${String(patient.age || '—')} / ${String(patient.gender || '—')}"`)
    csvRows.push('')

    // Itemized table
    csvRows.push(`"--- 3. ITEMIZED MEDICINES & BILLED ITEMS ---"`)
    csvRows.push(`"#","Medicine / Item Name","Unique Code / Batch","Strength","Unit Price / MRP","Quantity","Discount","Total Price / Amount"`)
    medicines.forEach((item, index) => {
      const name = String(item.medicine_name || item.item_name || item.description || item.name || '—').replace(/"/g, '""')
      const code = String(item.unique_code || item.batch_no || item.hsn_code || '—').replace(/"/g, '""')
      const strength = String(item.strength || item.frequency || '—').replace(/"/g, '""')
      const price = item.unit_price !== undefined ? String(item.unit_price) : '—'
      const qty = item.quantity !== undefined ? String(item.quantity) : '—'
      const disc = item.discount !== undefined ? String(item.discount) : '—'
      const total = item.total_price !== undefined ? String(item.total_price) : '—'
      csvRows.push(`"${index + 1}","${name}","${code}","${strength}","${price}","${qty}","${disc}","${total}"`)
    })
    csvRows.push('')

    // Financial totals
    if (Object.keys(billingSummary).length > 0) {
      csvRows.push(`"--- 4. FINANCIAL SUMMARY & TOTALS ---"`)
      csvRows.push(`"Subtotal / Taxable:","${String(billingSummary.subtotal || '—')}"`)
      csvRows.push(`"Total Discount:","${String(billingSummary.discount_total || '—')}"`)
      csvRows.push(`"Tax Amount / GST:","${String(billingSummary.tax_amount || '—')}"`)
      csvRows.push(`"GRAND TOTAL / NET PAYABLE:","${String(billingSummary.total_cost || billingSummary.grand_total || '—')}"`)
      csvRows.push(`"Payment Mode / Status:","${String(billingSummary.payment_mode || '—')} / ${String(billingSummary.payment_status || '—')}"`)
    }

    const csvBlob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(csvBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-3xl border border-slate-200 bg-white shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50/80">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-evergreen/10 text-evergreen shadow-xs">
              {activeFormat === 'excel' ? <FileSpreadsheet size={22} /> : <FileJson size={22} />}
            </div>
            <div>
              <h2 className="text-base font-bold text-ink">Export Medical Document & Bill</h2>
              <p className="text-xs text-slate-500 font-mono">
                {prescription?.original_filename || 'Prescription / Medical Bill'}
              </p>
            </div>
          </div>

          {/* Format Switcher Tabs */}
          <div className="flex items-center rounded-xl bg-slate-200/80 p-1">
            <button
              onClick={() => setActiveFormat('excel')}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                activeFormat === 'excel'
                  ? 'bg-white text-evergreen shadow-xs'
                  : 'text-slate-600 hover:text-ink'
              }`}
            >
              <FileSpreadsheet size={15} />
              <span>Excel (.xlsx)</span>
            </button>

            <button
              onClick={() => setActiveFormat('json')}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                activeFormat === 'json'
                  ? 'bg-white text-evergreen shadow-xs'
                  : 'text-slate-600 hover:text-ink'
              }`}
            >
              <FileJson size={15} />
              <span>JSON</span>
            </button>
          </div>
        </div>

        {/* Modal Body: Excel Preview or JSON Code */}
        <div className="flex-1 overflow-auto p-6 bg-slate-50/40">
          {activeFormat === 'excel' ? (
            <div className="space-y-5">
              {/* Top Banner Box */}
              <div className="rounded-2xl border border-teal-200/70 bg-gradient-to-r from-teal-50 to-emerald-50 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-teal-800">
                    <Table size={18} />
                    <span className="text-xs font-bold uppercase tracking-wider">
                      Structured Spreadsheet Preview
                    </span>
                  </div>
                  <span className="rounded-full bg-teal-200/60 px-2.5 py-0.5 font-mono text-[11px] font-bold text-teal-900">
                    {medicines.length} Item{medicines.length === 1 ? '' : 's'} Detected
                  </span>
                </div>
                <p className="mt-1 text-xs text-teal-950/80">
                  Ready to export in formatted <strong>Microsoft Excel (.xlsx)</strong> or CSV format with provider, patient, items, unique batch/codes, rates, and totals.
                </p>
              </div>

              {/* Provider & Patient Summary Cards */}
              <div className="grid gap-4 sm:grid-cols-2">
                {/* Provider Card */}
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                    Hospital & Doctor Information
                  </h3>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between py-1 border-b border-slate-100">
                      <span className="text-slate-500">Hospital / Pharmacy:</span>
                      <span className="font-semibold text-ink">{String(provider.hospital_name || provider.name || '—')}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-100">
                      <span className="text-slate-500">Doctor / Consultant:</span>
                      <span className="font-semibold text-ink">{String(provider.doctor_name || provider.doctor || '—')}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-100">
                      <span className="text-slate-500">Bill / Invoice No:</span>
                      <span className="font-mono font-semibold text-ink">{String(provider.bill_number || provider.invoice_no || '—')}</span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-slate-500">Receipt / Bill Date:</span>
                      <span className="font-medium text-ink">{String(provider.bill_date || provider.date || '—')}</span>
                    </div>
                  </div>
                </div>

                {/* Patient Card */}
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                    Patient & Customer Details
                  </h3>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between py-1 border-b border-slate-100">
                      <span className="text-slate-500">Patient Name:</span>
                      <span className="font-semibold text-ink">{String(patient.name || patient.patient_name || '—')}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-100">
                      <span className="text-slate-500">Patient ID / UHID:</span>
                      <span className="font-mono font-semibold text-ink">{String(patient.patient_id || patient.uhid || '—')}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-100">
                      <span className="text-slate-500">Age / Gender:</span>
                      <span className="font-medium text-ink">
                        {String(patient.age || '—')} {patient.gender ? `(${String(patient.gender)})` : ''}
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-slate-500">Total Bill Amount:</span>
                      <span className="font-bold text-evergreen">
                        {billingSummary.total_cost !== undefined ? `₹${billingSummary.total_cost}` : '—'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Items Table Preview */}
              <div className="rounded-2xl border border-slate-200 bg-white shadow-xs overflow-hidden">
                <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                    Itemized Medicines & Billed Products
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-slate-200 bg-slate-100/60 font-semibold text-slate-600">
                      <tr>
                        <th className="px-3.5 py-2.5">#</th>
                        <th className="px-3.5 py-2.5">Medicine / Item</th>
                        <th className="px-3.5 py-2.5">Batch / Code</th>
                        <th className="px-3.5 py-2.5 text-right">Unit Price</th>
                        <th className="px-3.5 py-2.5 text-center">Qty</th>
                        <th className="px-3.5 py-2.5 text-right">Total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {medicines.length > 0 ? (
                        medicines.map((item, idx) => (
                          <tr key={idx} className="hover:bg-slate-50/50">
                            <td className="px-3.5 py-2 font-mono text-slate-400">{idx + 1}</td>
                            <td className="px-3.5 py-2 font-semibold text-ink">
                              {String(item.medicine_name || item.item_name || item.description || item.name || '—')}
                            </td>
                            <td className="px-3.5 py-2 font-mono text-xs text-slate-500">
                              {String(item.unique_code || item.batch_no || item.hsn_code || '—')}
                            </td>
                            <td className="px-3.5 py-2 text-right font-mono">
                              {item.unit_price !== undefined ? `₹${item.unit_price}` : '—'}
                            </td>
                            <td className="px-3.5 py-2 text-center font-mono font-medium">
                              {item.quantity !== undefined ? String(item.quantity) : String(item.strength || '1')}
                            </td>
                            <td className="px-3.5 py-2 text-right font-mono font-bold text-ink">
                              {item.total_price !== undefined ? `₹${String(item.total_price)}` : '—'}
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={6} className="p-4 text-center text-slate-400">
                            No itemized medicine records found in this document.
                          </td>
                        </tr>
                      )}
                    </tbody>
                    {/* Table Footer with Totals */}
                    {Object.keys(billingSummary).length > 0 && (
                      <tfoot className="border-t border-slate-200 bg-slate-50/80 font-semibold text-xs">
                        {billingSummary.subtotal !== undefined && (
                          <tr>
                            <td colSpan={5} className="px-3.5 py-1.5 text-right text-slate-500">Subtotal:</td>
                            <td className="px-3.5 py-1.5 text-right font-mono text-ink">₹{String(billingSummary.subtotal)}</td>
                          </tr>
                        )}
                        {billingSummary.tax_amount !== undefined && (
                          <tr>
                            <td colSpan={5} className="px-3.5 py-1.5 text-right text-slate-500">Tax / GST:</td>
                            <td className="px-3.5 py-1.5 text-right font-mono text-ink">₹{String(billingSummary.tax_amount)}</td>
                          </tr>
                        )}
                        <tr>
                          <td colSpan={5} className="px-3.5 py-2.5 text-right font-bold text-evergreen">GRAND TOTAL:</td>
                          <td className="px-3.5 py-2.5 text-right font-mono font-extrabold text-sm text-evergreen">
                            ₹{String(billingSummary.total_cost ?? billingSummary.grand_total ?? '—')}
                          </td>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-900 bg-slate-950 p-5 text-slate-200 shadow-inner">
              <pre className="font-mono text-xs leading-5 select-all overflow-auto max-h-[50vh]">
                {jsonContent}
              </pre>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between border-t border-slate-200 bg-white px-6 py-4">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Layers size={15} />
            <span>{fieldsData?.fields.length || 0} fields mapped</span>
          </div>

          <div className="flex items-center gap-2.5">
            {activeFormat === 'json' ? (
              <>
                <button
                  onClick={handleCopy}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 active:scale-95 transition"
                >
                  {copied ? <Check size={14} className="text-evergreen" /> : <Copy size={14} />}
                  <span>{copied ? 'Copied' : 'Copy JSON'}</span>
                </button>

                <button
                  onClick={handleDownloadJson}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-evergreen px-4 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-ink active:scale-95 transition"
                >
                  <Download size={14} />
                  <span>Download JSON</span>
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={handleDownloadCsv}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 active:scale-95 transition"
                >
                  <Download size={14} />
                  <span>Download CSV</span>
                </button>

                <button
                  disabled={downloading}
                  onClick={() => void handleDownloadExcel()}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-evergreen px-5 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-ink active:scale-95 transition disabled:opacity-50"
                >
                  <Download size={14} />
                  <span>{downloading ? 'Generating Excel…' : 'Download Excel (.xlsx)'}</span>
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 transition"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
