/**
 * @file 大纲节点表单字段
 */
import clsx from 'clsx'

export function Field({
  label, sublabel, value, editing, onChange, singleLine = false,
}: {
  label: string
  sublabel?: string
  value: string
  editing: boolean
  onChange: (v: string) => void
  singleLine?: boolean
}) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1">
        <label className="text-xs font-medium text-gray-600">{label}</label>
        {sublabel && <span className="text-[10px] text-gray-400">{sublabel}</span>}
      </div>
      {editing ? (
        singleLine ? (
          <input value={value} onChange={e => onChange(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300" />
        ) : (
          <textarea value={value} onChange={e => onChange(e.target.value)} rows={3}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300 resize-y" />
        )
      ) : (
        <div className={clsx(
          'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50 whitespace-pre-wrap',
          singleLine ? 'text-gray-800' : 'text-gray-700 min-h-[64px]'
        )}>
          {value || <span className="text-gray-400 italic">—</span>}
        </div>
      )}
    </div>
  )
}
