import { render, screen } from '@testing-library/react'

import { RawOCRPanel } from './RawOCRPanel'

test('shows persisted provider text and real confidence', () => {
  render(<RawOCRPanel ocr={{ prescription_id: 'rx-1', results: [{ id: 'result-1', page_id: 'page-1', provider: 'tesseract', provider_version: '5', raw_text: 'Patient Evidence', confidence: 0.82, processing_ms: 14, metadata: {}, tokens: [] }] }} />)
  expect(screen.getByText('Patient Evidence')).toBeInTheDocument()
  expect(screen.getByText('tesseract')).toBeInTheDocument()
  expect(screen.getByText('82%')).toBeInTheDocument()
})

test('does not fabricate confidence when the provider omitted it', () => {
  render(<RawOCRPanel ocr={{ prescription_id: 'rx-1', results: [{ id: 'result-1', page_id: 'page-1', provider: 'pdf_text', provider_version: null, raw_text: 'Typed layer', confidence: null, processing_ms: 0, metadata: {}, tokens: [] }] }} />)
  expect(screen.queryByText(/%/)).not.toBeInTheDocument()
})

