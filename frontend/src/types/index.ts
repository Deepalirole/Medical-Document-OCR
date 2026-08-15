export type OrganizationRole = 'admin' | 'reviewer'

export interface Membership {
  organization_id: string
  organization_name: string
  role: OrganizationRole
}

export interface CurrentUser {
  id: string
  email: string | null
  display_name: string | null
  memberships: Membership[]
}

export interface Organization {
  id: string
  name: string
}

export interface PrescriptionSchema {
  id: string
  organization_id: string
  schema_key: string
  name: string
  version: number
  status: string
  is_active: boolean
  definition: Record<string, unknown>
}

export interface Prescription {
  id: string
  organization_id: string
  schema_id: string
  original_filename: string
  source_mime_type: string
  source_type: 'pdf' | 'image'
  status: string
  page_count: number
  duplicate: boolean
  created_at?: string | null
}

export interface OrganizationMetrics {
  processed_count: number
  ocr_failures: number
  llm_failures: number
  review_required_count: number
  approved_count: number
  correction_count: number
  average_processing_ms: number
}

export interface PrescriptionPage {
  id: string
  page_number: number
  width: number
  height: number
  quality_metadata: Record<string, number | boolean>
  preprocessing_applied: string[]
  status: string
  preview_url: string | null
}

export interface PrescriptionDetail extends Prescription {
  pages: PrescriptionPage[]
}

export interface ProcessingJob {
  id: string
  stage: string
  status: string
  attempt: number
  processing_ms: number | null
  error_code: string | null
  safe_error_message: string | null
  metadata: Record<string, unknown>
}

export interface ProcessingStatus {
  prescription_id: string
  status: string
  jobs: ProcessingJob[]
}

export interface OCRToken {
  text: string
  confidence: number | null
  bbox: { x1: number; y1: number; x2: number; y2: number } | null
  sequence_index: number
  source: 'ocr' | 'htr' | 'pdf_text'
}

export interface OCRResult {
  id: string
  page_id: string
  provider: string
  provider_version: string | null
  raw_text: string
  confidence: number | null
  processing_ms: number
  metadata: Record<string, unknown>
  tokens: OCRToken[]
}

export interface OCRResponse {
  prescription_id: string
  results: OCRResult[]
}

export interface PrescriptionField {
  id: string
  prescription_id: string
  schema_id: string
  field_path: string
  field_type: string
  array_item_id: string | null
  original_value: unknown
  current_value: unknown
  review_status: 'HIGH' | 'MEDIUM' | 'LOW' | 'REVIEW_REQUIRED'
  confidence: number | null
  evidence: Array<Record<string, unknown>> | null
  validation: { valid?: boolean; warnings?: string[] }
}

export interface FieldsResponse {
  prescription_id: string
  schema_definition: {
    schema_key?: string
    version?: number
    sections: Array<Record<string, unknown>>
  }
  structured_json: Record<string, unknown>
  fields: PrescriptionField[]
}

export interface ApprovedVersion {
  id: string
  prescription_id: string
  schema_id: string
  schema_version: number
  version: number
  structured_json: Record<string, unknown>
  status: 'APPROVED'
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> }
}
