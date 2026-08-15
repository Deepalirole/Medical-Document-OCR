import type {
  ApiErrorBody,
  CurrentUser,
  FieldsResponse,
  OCRResponse,
  Organization,
  OrganizationMetrics,
  Prescription,
  PrescriptionDetail,
  PrescriptionSchema,
  PrescriptionField,
  ProcessingStatus,
  ApprovedVersion,
} from '../types'
import { supabase } from './supabase'

const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  (import.meta.env.DEV ? '' : `http://${window.location.hostname}:8000`)

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { data } = await supabase.auth.getSession()
  const accessToken = data.session?.access_token
  if (!accessToken) throw new ApiError('AUTHENTICATION_REQUIRED', 'Please sign in.', 401)

  const requestOptions: RequestInit = {
    ...options,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  }
  const retryable = !options.method || options.method === 'GET'
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, requestOptions)
  } catch {
    if (!retryable) {
      throw new ApiError('API_UNREACHABLE', 'The API server is temporarily unreachable.', 0)
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500))
    try {
      response = await fetch(`${apiBaseUrl}${path}`, requestOptions)
    } catch {
      throw new ApiError(
        'API_UNREACHABLE',
        'The API server is temporarily unreachable. Please retry in a moment.',
        0,
      )
    }
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null
    throw new ApiError(
      body?.error.code || 'REQUEST_FAILED',
      body?.error.message || 'The request could not be completed.',
      response.status,
    )
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  me: () => request<CurrentUser>('/api/me'),
  organizations: () => request<Organization[]>('/api/organizations'),
  schemas: () => request<PrescriptionSchema[]>('/api/prescription-schemas'),
  upload: (organizationId: string, schemaId: string, file: File) => {
    const body = new FormData()
    body.append('organization_id', organizationId)
    body.append('schema_id', schemaId)
    body.append('file', file)
    return request<Prescription>('/api/prescriptions', { method: 'POST', body })
  },
  process: (prescriptionId: string) =>
    request<{ prescription_id: string; status: string }>(`/api/prescriptions/${prescriptionId}/process`, { method: 'POST' }),
  prescription: (prescriptionId: string) =>
    request<PrescriptionDetail>(`/api/prescriptions/${prescriptionId}`),
  processingStatus: (prescriptionId: string) =>
    request<ProcessingStatus>(`/api/prescriptions/${prescriptionId}/status`),
  ocr: (prescriptionId: string) =>
    request<OCRResponse>(`/api/prescriptions/${prescriptionId}/ocr`),
  fields: (prescriptionId: string) =>
    request<FieldsResponse>(`/api/prescriptions/${prescriptionId}/fields`),
  correctField: (prescriptionId: string, fieldId: string, value: unknown, reason?: string) =>
    request<PrescriptionField>(`/api/prescriptions/${prescriptionId}/fields/${fieldId}`, {
      method: 'PATCH',
      body: JSON.stringify({ value, reason: reason || null }),
    }),
  mutateFields: (
    prescriptionId: string,
    payload: {
      updates?: Array<[string, unknown, string | null]>
      add_items?: Array<{ array_path: string; values: Record<string, unknown> }>
      remove_item_ids?: string[]
    },
  ) => request<PrescriptionField[]>(`/api/prescriptions/${prescriptionId}/fields`, { method: 'PATCH', body: JSON.stringify(payload) }),
  approve: (prescriptionId: string) =>
    request<ApprovedVersion>(`/api/prescriptions/${prescriptionId}/approve`, { method: 'POST' }),
  finalJson: (prescriptionId: string) =>
    request<Record<string, unknown>>(`/api/prescriptions/${prescriptionId}/json`),
  prescriptions: (organizationId: string, limit = 25, createdBefore?: string) => {
    const query = new URLSearchParams({ organization_id: organizationId, limit: String(limit) })
    if (createdBefore) query.set('created_before', createdBefore)
    return request<Prescription[]>(`/api/prescriptions?${query}`)
  },
  metrics: (organizationId: string) =>
    request<OrganizationMetrics>(`/api/organizations/${organizationId}/metrics`),
  createSchema: (payload: { organization_id: string; schema_key: string; name: string; version: number; definition: Record<string, unknown> }) =>
    request<PrescriptionSchema>('/api/prescription-schemas', { method: 'POST', body: JSON.stringify(payload) }),
  updateSchema: (schemaId: string, payload: { name: string; definition: Record<string, unknown> }) =>
    request<PrescriptionSchema>(`/api/prescription-schemas/${schemaId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  activateSchema: (schemaId: string) =>
    request<PrescriptionSchema>(`/api/prescription-schemas/${schemaId}/activate`, { method: 'POST' }),
  deleteSchema: (schemaId: string) =>
    request<void>(`/api/prescription-schemas/${schemaId}`, { method: 'DELETE' }),
}
