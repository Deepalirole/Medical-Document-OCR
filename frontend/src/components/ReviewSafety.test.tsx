import { render, screen } from '@testing-library/react'

import type { FieldsResponse, PrescriptionField } from '../types'
import { ConfidenceBadge } from './ConfidenceBadge'
import { ValidationPanel } from './ValidationPanel'

const uncertainField: PrescriptionField = {
  id: 'field-1',
  prescription_id: 'rx-1',
  schema_id: 'schema-1',
  field_path: 'medicines[0].medicine_name',
  field_type: 'string',
  array_item_id: 'row-1',
  original_value: 'Unclear',
  current_value: 'Unclear',
  review_status: 'REVIEW_REQUIRED',
  confidence: null,
  evidence: [],
  validation: { valid: false, warnings: ['VALUE_HAS_NO_MATCHING_EVIDENCE'] },
}

test('uncertain medication field never displays fabricated numeric confidence', () => {
  render(<ConfidenceBadge field={uncertainField} />)
  expect(screen.getByText('Review required')).toBeInTheDocument()
  expect(screen.queryByText(/%/)).not.toBeInTheDocument()
})

test('validation gate reports unresolved field and warning', () => {
  const data: FieldsResponse = {
    prescription_id: 'rx-1',
    schema_definition: { sections: [] },
    structured_json: {},
    fields: [uncertainField],
  }
  render(<ValidationPanel data={data} />)
  expect(screen.getByText('1 field need review')).toBeInTheDocument()
  expect(screen.getByText(/value has no matching evidence/i)).toBeInTheDocument()
})

