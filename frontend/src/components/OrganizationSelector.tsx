import { Building2, ChevronDown } from 'lucide-react'

import type { Organization } from '../types'

interface Props {
  organizations: Organization[]
  value: string
  onChange: (organizationId: string) => void
}

export function OrganizationSelector({ organizations, value, onChange }: Props) {
  return (
    <label className="relative flex items-center gap-2 text-sm">
      <Building2 size={16} aria-hidden="true" />
      <span className="sr-only">Organization</span>
      <select className="appearance-none bg-transparent py-2 pl-1 pr-7 font-medium outline-none" value={value} onChange={(event) => onChange(event.target.value)}>
        {organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
      </select>
      <ChevronDown className="pointer-events-none absolute right-0" size={15} />
    </label>
  )
}

