import {
  BrainCircuit,
  Building2,
  Database,
  Download,
  FileCode2,
  FileSpreadsheet,
  FileStack,
  FileText,
  LogOut,
  Plus,
  Settings2,
} from 'lucide-react'

import type { CurrentUser, Organization } from '../types'
import { supabase } from '../lib/supabase'

export type NavTab = 'review' | 'queue' | 'ocr' | 'tables' | 'export' | 'schemas'

export function Sidebar({
  activeTab,
  onTabChange,
  onNewPrescription,
  organizations,
  currentOrgId,
  onOrgChange,
  user,
  prescriptionCount,
}: {
  activeTab: NavTab
  onTabChange: (tab: NavTab) => void
  onNewPrescription: () => void
  organizations: Organization[]
  currentOrgId: string
  onOrgChange: (orgId: string) => void
  user: CurrentUser | null
  prescriptionCount: number
}) {
  const isAdmin =
    user?.memberships.some(
      (membership) => membership.organization_id === currentOrgId && membership.role === 'admin',
    ) || false

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-slate-200 bg-white text-ink">
      {/* Brand Header */}
      <div className="flex items-center gap-3 border-b border-slate-200/80 px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-evergreen text-white shadow-sm">
          <BrainCircuit size={20} />
        </div>
        <div>
          <p className="text-sm font-bold tracking-tight text-ink">Intelligence Studio</p>
          <p className="text-[11px] font-medium text-slate-500">Medical Document OCR</p>
        </div>
      </div>

      {/* Quick Action */}
      <div className="p-4">
        <button
          onClick={onNewPrescription}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-evergreen px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-ink hover:shadow active:scale-[0.98]"
        >
          <Plus size={16} />
          <span>New Prescription</span>
        </button>
      </div>

      {/* Navigation Sections */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-6">
        {/* Workspace */}
        <div>
          <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Workspace
          </p>
          <nav className="mt-2 space-y-1">
            <button
              onClick={() => onTabChange('review')}
              className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-xs font-medium transition ${
                activeTab === 'review'
                  ? 'bg-evergreen/10 font-semibold text-evergreen'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-ink'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <FileText size={16} className={activeTab === 'review' ? 'text-evergreen' : 'text-slate-400'} />
                <span>Document Review</span>
              </div>
            </button>

            <button
              onClick={() => onTabChange('queue')}
              className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-xs font-medium transition ${
                activeTab === 'queue'
                  ? 'bg-evergreen/10 font-semibold text-evergreen'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-ink'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <FileStack size={16} className={activeTab === 'queue' ? 'text-evergreen' : 'text-slate-400'} />
                <span>Prescriptions Queue</span>
              </div>
              {prescriptionCount > 0 && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-600">
                  {prescriptionCount}
                </span>
              )}
            </button>
          </nav>
        </div>

        {/* Extraction & Intelligence */}
        <div>
          <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Extraction
          </p>
          <nav className="mt-2 space-y-1">
            <button
              onClick={() => onTabChange('review')}
              className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-medium transition ${
                activeTab === 'review'
                  ? 'text-slate-700 font-semibold'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-ink'
              }`}
            >
              <FileCode2 size={16} className="text-slate-400" />
              <span>Extracted Fields</span>
            </button>

            <button
              onClick={() => onTabChange('ocr')}
              className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-medium transition ${
                activeTab === 'ocr'
                  ? 'bg-evergreen/10 font-semibold text-evergreen'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-ink'
              }`}
            >
              <Database size={16} className={activeTab === 'ocr' ? 'text-evergreen' : 'text-slate-400'} />
              <span>Raw OCR Layer</span>
            </button>

            <button
              onClick={() => onTabChange('tables')}
              className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-medium transition ${
                activeTab === 'tables'
                  ? 'bg-evergreen/10 font-semibold text-evergreen'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-ink'
              }`}
            >
              <FileSpreadsheet size={16} className={activeTab === 'tables' ? 'text-evergreen' : 'text-slate-400'} />
              <span>Medicines & Tables</span>
            </button>

            <button
              onClick={() => onTabChange('export')}
              className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-medium transition ${
                activeTab === 'export'
                  ? 'bg-evergreen/10 font-semibold text-evergreen'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-ink'
              }`}
            >
              <Download size={16} className={activeTab === 'export' ? 'text-evergreen' : 'text-slate-400'} />
              <span>Downloads & Export</span>
            </button>
          </nav>
        </div>

        {/* Management */}
        <div>
          <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Management
          </p>
          <nav className="mt-2 space-y-1">
            {isAdmin && (
              <button
                onClick={() => onTabChange('schemas')}
                className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-medium transition ${
                  activeTab === 'schemas'
                    ? 'bg-evergreen/10 font-semibold text-evergreen'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-ink'
                }`}
              >
                <Settings2 size={16} className={activeTab === 'schemas' ? 'text-evergreen' : 'text-slate-400'} />
                <span>Schema Registry</span>
              </button>
            )}
          </nav>
        </div>
      </div>

      {/* Footer: Organization & User Profile */}
      <div className="border-t border-slate-200 bg-slate-50/70 p-3 space-y-2.5">
        {/* Org Selector */}
        <div className="flex items-center gap-2 rounded-xl bg-white p-2 border border-slate-200 shadow-sm">
          <Building2 size={16} className="text-slate-400 shrink-0" />
          <select
            aria-label="Select organization"
            className="w-full bg-transparent text-xs font-semibold text-ink focus:outline-none cursor-pointer"
            value={currentOrgId}
            onChange={(e) => onOrgChange(e.target.value)}
          >
            {organizations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
        </div>

        {/* User Card & Sign Out */}
        <div className="flex items-center justify-between px-1">
          <div className="truncate">
            <p className="truncate text-xs font-semibold text-ink">
              {user?.display_name || user?.email?.split('@')[0] || 'User'}
            </p>
            <p className="truncate text-[10px] text-slate-400">{user?.email}</p>
          </div>
          <button
            onClick={() => void supabase.auth.signOut()}
            title="Sign out"
            aria-label="Sign out"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white hover:text-red-600 hover:shadow-sm"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  )
}
