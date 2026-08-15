import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'

import { OrganizationSelector } from './OrganizationSelector'

test('changes the active organization explicitly', () => {
  const onChange = vi.fn()
  render(<OrganizationSelector organizations={[{ id: 'org-a', name: 'Clinic A' }, { id: 'org-b', name: 'Clinic B' }]} value="org-a" onChange={onChange} />)
  fireEvent.change(screen.getByRole('combobox', { name: 'Organization' }), { target: { value: 'org-b' } })
  expect(onChange).toHaveBeenCalledWith('org-b')
})

