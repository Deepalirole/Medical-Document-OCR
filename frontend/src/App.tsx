import { useEffect, useMemo, useState } from 'react'
import { Plus, Search } from 'lucide-react'

import { ExportModal } from './components/ExportModal'
import { MedicineTableView } from './components/MedicineTableView'
import { PageStrip } from './components/PageStrip'
import { PrescriptionUploader } from './components/PrescriptionUploader'
import { PrescriptionViewer } from './components/PrescriptionViewer'
import { RawOCRPanel } from './components/RawOCRPanel'
import { ReviewMatrix } from './components/ReviewMatrix'
import { SchemaManager } from './components/SchemaManager'
import { Sidebar, type NavTab } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { api } from './lib/api'
import type {
  ApprovedVersion,
  CurrentUser,
  FieldsResponse,
  OCRResponse,
  Organization,
  OrganizationMetrics,
  Prescription,
  PrescriptionDetail,
  PrescriptionSchema,
  ProcessingStatus as Status,
} from './types'

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [schemas, setSchemas] = useState<PrescriptionSchema[]>([])
  const [organizationId, setOrganizationId] = useState('')
  const [activeTab, setActiveTab] = useState<NavTab>('review')

  const [showUploader, setShowUploader] = useState(false)
  const [showExportModal, setShowExportModal] = useState(false)

  const [selected, setSelected] = useState<Prescription | null>(null)
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([])
  const [metrics, setMetrics] = useState<OrganizationMetrics | null>(null)
  const [detail, setDetail] = useState<PrescriptionDetail | null>(null)
  const [processingStatus, setProcessingStatus] = useState<Status | null>(null)
  const [ocr, setOcr] = useState<OCRResponse | null>(null)
  const [fields, setFields] = useState<FieldsResponse | null>(null)
  const [approved, setApproved] = useState<ApprovedVersion | null>(null)
  const [activePageIndex, setActivePageIndex] = useState(0)

  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState('')
  const [queueSearch, setQueueSearch] = useState('')
  const [queueStatusFilter, setQueueStatusFilter] = useState('ALL')

  // Initial load
  useEffect(() => {
    void Promise.all([api.me(), api.organizations(), api.schemas()])
      .then(([me, orgs, schemaRows]) => {
        setUser(me)
        setOrganizations(orgs)
        setSchemas(schemaRows)
        if (orgs[0]) setOrganizationId(orgs[0].id)
      })
      .catch((requestError: Error) => setError(requestError.message))
  }, [])

  // Load prescriptions when organization changes
  useEffect(() => {
    if (!organizationId) return
    void Promise.all([api.prescriptions(organizationId), api.metrics(organizationId)])
      .then(([rows, organizationMetrics]) => {
        setPrescriptions(rows)
        setMetrics(organizationMetrics)
        if (rows.length > 0 && !selected) {
          setSelected(rows[0])
          void refresh(rows[0].id)
        }
      })
      .catch((requestError: Error) => setError(requestError.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationId])

  async function refreshSchemas() {
    setSchemas(await api.schemas())
  }

  async function refresh(prescriptionId: string) {
    try {
      const [nextDetail, nextStatus, nextOcr, nextFields] = await Promise.all([
        api.prescription(prescriptionId),
        api.processingStatus(prescriptionId),
        api.ocr(prescriptionId),
        api.fields(prescriptionId),
      ])
      setDetail(nextDetail)
      setProcessingStatus(nextStatus)
      setOcr(nextOcr)
      setFields(nextFields)
      setSelected(nextDetail)
    } catch (fetchErr) {
      setError(fetchErr instanceof Error ? fetchErr.message : 'Could not refresh prescription.')
    }
  }

  async function processCurrent() {
    if (!selected) return
    setProcessing(true)
    setError('')
    try {
      await api.process(selected.id)
      await refresh(selected.id)
    } catch (processError) {
      setError(processError instanceof Error ? processError.message : 'Processing failed.')
      try {
        setProcessingStatus(await api.processingStatus(selected.id))
      } catch {
        /* retain error */
      }
    } finally {
      setProcessing(false)
    }
  }

  async function handleConfirmAll() {
    if (!selected || !fields) return
    setProcessing(true)
    try {
      const candidateList = fields.fields
      const toConfirm = candidateList.filter((f) => f.review_status !== 'HIGH')
      const targetList = toConfirm.length > 0 ? toConfirm : candidateList
      if (targetList.length > 0) {
        const updates = targetList.map(
          (f) => [f.id, f.current_value, 'Batch confirmed by reviewer'] as [string, unknown, string | null],
        )
        await api.mutateFields(selected.id, { updates })
      }
      await refresh(selected.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Confirm all failed.')
    } finally {
      setProcessing(false)
    }
  }

  async function handleApprove() {
    if (!selected) return
    setProcessing(true)
    try {
      if (fields) {
        const unconfirmed = fields.fields.filter((f) => f.review_status !== 'HIGH')
        if (unconfirmed.length > 0) {
          const updates = unconfirmed.map(
            (f) => [f.id, f.current_value, 'Confirmed on approval'] as [string, unknown, string | null],
          )
          await api.mutateFields(selected.id, { updates })
        }
      }
      const version = await api.approve(selected.id)
      setApproved(version)
      await refresh(selected.id)
    } catch (approveErr) {
      setError(approveErr instanceof Error ? approveErr.message : 'Approval failed.')
    } finally {
      setProcessing(false)
    }
  }

  function handleCreated(prescription: Prescription) {
    setSelected(prescription)
    setShowUploader(false)
    setDetail(null)
    setProcessingStatus({ prescription_id: prescription.id, status: prescription.status, jobs: [] })
    setOcr(null)
    setFields(null)
    setApproved(null)
    setActiveTab('review')
    setPrescriptions((rows) => [prescription, ...rows.filter((row) => row.id !== prescription.id)])
    // Automatically trigger background document processing and extraction
    setProcessing(true)
    api
      .process(prescription.id)
      .then(() => refresh(prescription.id))
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Processing failed.')
      })
      .finally(() => {
        setProcessing(false)
      })
  }

  const filteredQueue = useMemo(() => {
    return prescriptions.filter((p) => {
      if (queueSearch.trim()) {
        const q = queueSearch.toLowerCase()
        if (!p.original_filename.toLowerCase().includes(q) && !p.id.toLowerCase().includes(q))
          return false
      }
      if (queueStatusFilter !== 'ALL' && p.status !== queueStatusFilter) return false
      return true
    })
  }, [prescriptions, queueSearch, queueStatusFilter])

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-100 font-sans text-ink">
      {/* 1. Left Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={(tab) => {
          if (tab === 'export') {
            setShowExportModal(true)
          } else {
            setActiveTab(tab)
          }
        }}
        onNewPrescription={() => setShowUploader(true)}
        organizations={organizations}
        currentOrgId={organizationId}
        onOrgChange={(id) => {
          setOrganizationId(id)
          setSelected(null)
          setDetail(null)
        }}
        user={user}
        prescriptionCount={prescriptions.length}
      />

      {/* 2. Main Studio Work Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Intelligence & Control Bar */}
        <TopBar
          prescription={detail}
          processingStatus={processingStatus}
          ocr={ocr}
          fields={fields}
          isApproved={detail?.status === 'APPROVED' || !!approved}
          isProcessing={processing}
          dirtyCount={0}
          onRunOCR={() => void processCurrent()}
          onSaveCorrections={() => {}}
          onConfirmAll={() => void handleConfirmAll()}
          onApprove={() => void handleApprove()}
          onExport={() => setShowExportModal(true)}
        />

        {/* Global Error Banner */}
        {error && (
          <div
            role="alert"
            className="flex items-center justify-between border-b border-red-200 bg-red-50 px-6 py-2.5 text-xs font-semibold text-red-700"
          >
            <span>{error}</span>
            <button onClick={() => setError('')} className="text-red-500 hover:text-red-800">
              ✕
            </button>
          </div>
        )}

        {/* Dynamic Main Workspace Tabs */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* TAB 1: DOCUMENT REVIEW (SPLIT VIEW) */}
          {activeTab === 'review' && (
            <div className="flex flex-1 flex-col overflow-hidden">
              {/* Document Page Strip */}
              <PageStrip
                prescription={detail}
                ocr={ocr}
                currentPageIndex={activePageIndex}
                onSelectPage={(idx) => setActivePageIndex(idx)}
              />

              {/* Split Main Area: Left Viewer + Right Review Matrix */}
              <div className="grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[1.1fr_0.9fr]">
                {/* Left Pane: High-Res Document Canvas */}
                <div className="border-r border-slate-200 overflow-hidden flex flex-col bg-white">
                  <PrescriptionViewer
                    prescription={detail}
                    pageIndex={activePageIndex}
                    onPageChange={(idx) => setActivePageIndex(idx)}
                  />
                </div>

                {/* Right Pane: Intelligent Review Matrix */}
                <div className="overflow-hidden flex flex-col bg-white">
                  <ReviewMatrix
                    prescriptionId={selected?.id || ''}
                    fieldsData={fields}
                    activePageIndex={activePageIndex}
                    isProcessing={processing}
                    onRunExtraction={processCurrent}
                    onChanged={() => {
                      if (selected) void refresh(selected.id)
                    }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: PRESCRIPTION QUEUE */}
          {activeTab === 'queue' && (
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Metrics Summary Strip */}
              {metrics && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    ['Processed', metrics.processed_count, 'text-evergreen'],
                    ['Needs review', metrics.review_required_count, 'text-amber-600'],
                    ['Approved', metrics.approved_count, 'text-emerald-600'],
                    ['Corrections', metrics.correction_count, 'text-blue-600'],
                  ].map(([label, value, colorClass]) => (
                    <div
                      key={String(label)}
                      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
                    >
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        {label}
                      </p>
                      <p className={`mt-2 text-3xl font-extrabold ${colorClass}`}>{value}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Queue Controls & Filter */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
                  <h2 className="text-base font-bold text-ink">Prescription Queue</h2>

                  <div className="flex items-center gap-2.5">
                    {/* Search */}
                    <div className="relative min-w-56">
                      <Search className="absolute left-3 top-2.5 text-slate-400" size={14} />
                      <input
                        type="text"
                        placeholder="Search filename or ID…"
                        value={queueSearch}
                        onChange={(e) => setQueueSearch(e.target.value)}
                        className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-1.5 pl-9 pr-3 text-xs focus:border-evergreen focus:bg-white focus:outline-none"
                      />
                    </div>

                    {/* Status Filter */}
                    <select
                      aria-label="Filter queue by status"
                      value={queueStatusFilter}
                      onChange={(e) => setQueueStatusFilter(e.target.value)}
                      className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm focus:outline-none cursor-pointer"
                    >
                      <option value="ALL">All statuses</option>
                      <option value="REVIEW_REQUIRED">Needs review</option>
                      <option value="APPROVED">Approved</option>
                      <option value="UPLOADED">Uploaded</option>
                    </select>

                    <button
                      onClick={() => setShowUploader(true)}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-evergreen px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-ink"
                    >
                      <Plus size={14} />
                      <span>New Upload</span>
                    </button>
                  </div>
                </div>

                {/* Queue Table */}
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-slate-100 font-bold uppercase tracking-wider text-slate-400">
                      <tr>
                        <th className="py-3 px-3">Document</th>
                        <th className="py-3 px-3">Status</th>
                        <th className="py-3 px-3">Pages</th>
                        <th className="py-3 px-3">Type</th>
                        <th className="py-3 px-3">Created</th>
                        <th className="py-3 px-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-medium">
                      {filteredQueue.map((prescription) => (
                        <tr
                          key={prescription.id}
                          className="hover:bg-slate-50/70 transition cursor-pointer"
                          onClick={() => {
                            setSelected(prescription)
                            setActiveTab('review')
                            void refresh(prescription.id)
                          }}
                        >
                          <td className="py-3 px-3">
                            <p className="font-bold text-ink truncate max-w-xs">
                              {prescription.original_filename}
                            </p>
                            <p className="font-mono text-[10px] text-slate-400">
                              {prescription.id.slice(0, 13)}…
                            </p>
                          </td>
                          <td className="py-3 px-3">
                            <span
                              className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                                prescription.status === 'APPROVED'
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : prescription.status === 'REVIEW_REQUIRED'
                                    ? 'bg-amber-100 text-amber-800'
                                    : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              {prescription.status.replaceAll('_', ' ')}
                            </span>
                          </td>
                          <td className="py-3 px-3 font-mono">{prescription.page_count}</td>
                          <td className="py-3 px-3 uppercase font-mono text-[11px] text-slate-500">
                            {prescription.source_type}
                          </td>
                          <td className="py-3 px-3 text-slate-500">
                            {prescription.created_at
                              ? new Date(prescription.created_at).toLocaleDateString()
                              : '—'}
                          </td>
                          <td className="py-3 px-3 text-right">
                            <button className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-bold text-evergreen hover:bg-evergreen hover:text-white transition">
                              Open Review
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {filteredQueue.length === 0 && (
                    <p className="py-8 text-center text-xs text-slate-400">
                      No prescriptions found matching criteria.
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: RAW OCR LAYER */}
          {activeTab === 'ocr' && (
            <div className="flex-1 overflow-hidden">
              <RawOCRPanel ocr={ocr} />
            </div>
          )}

          {/* TAB 4: MEDICINES & REPEATABLE TABLES */}
          {activeTab === 'tables' && (
            <div className="flex-1 overflow-hidden">
              <MedicineTableView
                prescriptionId={selected?.id || ''}
                fieldsData={fields}
                onChanged={() => {
                  if (selected) void refresh(selected.id)
                }}
              />
            </div>
          )}

          {/* TAB 5: SCHEMA REGISTRY */}
          {activeTab === 'schemas' && (
            <div className="flex-1 overflow-y-auto p-6">
              <SchemaManager
                organizationId={organizationId}
                schemas={schemas}
                onClose={() => setActiveTab('review')}
                onChanged={() => void refreshSchemas()}
              />
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {showUploader && (
        <PrescriptionUploader
          organizationId={organizationId}
          schemas={schemas}
          onClose={() => setShowUploader(false)}
          onCreated={handleCreated}
        />
      )}

      {showExportModal && (
        <ExportModal
          prescription={detail}
          fieldsData={fields}
          onClose={() => setShowExportModal(false)}
        />
      )}
    </div>
  )
}

