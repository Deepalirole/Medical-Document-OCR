import type { FieldsResponse, PrescriptionField } from '../types'
import { FieldEditor } from './FieldEditor'
import { MedicineListEditor } from './MedicineListEditor'

interface SchemaNode {
  key: string
  type: string
  fields?: SchemaNode[]
  item_schema?: Record<string, { type: string; required?: boolean }>
}

export function DynamicFieldRenderer({ prescriptionId, data, onChanged }: { prescriptionId: string; data: FieldsResponse | null; onChanged: () => void }) {
  if (!data) return <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-slate-200 text-sm text-slate-500">Dynamic fields appear after extraction begins.</div>
  const sections = data.schema_definition.sections as unknown as SchemaNode[]

  function scalar(field: PrescriptionField | undefined, label: string) {
    return field ? <FieldEditor key={field.id} prescriptionId={prescriptionId} field={field} label={label} onSaved={onChanged} /> : null
  }

  return <div className="space-y-5">{sections.map((section) => {
    if (section.type === 'object') return <section key={section.key}><h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">{section.key.replaceAll('_', ' ')}</h3><div className="grid gap-3 sm:grid-cols-2">{section.fields?.map((child) => scalar(data.fields.find((field) => field.field_path === `${section.key}.${child.key}`), child.key))}</div></section>
    if ((section.type === 'array' || section.type === 'medicine_list') && section.item_schema && !('type' in section.item_schema)) return <MedicineListEditor key={section.key} prescriptionId={prescriptionId} node={section as SchemaNode & { item_schema: Record<string, { type: string; required?: boolean }> }} fields={data.fields} onChanged={onChanged} />
    if (section.type === 'array') {
      const itemFields = data.fields.filter((field) => field.field_path.startsWith(`${section.key}[`))
      return <section key={section.key} className="rounded-2xl border border-slate-200 p-4"><h3 className="mb-3 font-semibold capitalize">{section.key.replaceAll('_', ' ')}</h3><div className="space-y-3">{itemFields.map((field, index) => scalar(field, `${section.key} ${index + 1}`))}</div></section>
    }
    return scalar(data.fields.find((field) => field.field_path === section.key), section.key)
  })}</div>
}

