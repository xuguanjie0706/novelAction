/**
 * @file pages/Dabai/detail/blocks.tsx
 * 大白文「我的小说」详情页的共享展示原子组件。
 *
 * 职责：提供卡片 / 字段表 / 标签 / 空态等无业务状态的纯展示件，
 * 供各分区渲染复用，统一 rose（爽点红）视觉语言——区别于精品文纪要页的棕金风。
 * 禁止在此文件写数据获取或路由逻辑。
 */
import type { ReactNode } from 'react'

/** 内容卡片：白底圆角，标题行可选条目数 badge。 */
export function Card({
  title,
  count,
  hint,
  children,
}: {
  title?: string
  count?: number
  hint?: string
  children: ReactNode
}) {
  return (
    <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
      {title ? (
        <div className="mb-3 flex items-center gap-2">
          <h3 className="text-sm font-bold text-gray-900">{title}</h3>
          {typeof count === 'number' && count > 0 ? (
            <span className="rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-600">
              {count}
            </span>
          ) : null}
          {hint ? <span className="ml-auto text-[11px] text-gray-400">{hint}</span> : null}
        </div>
      ) : null}
      {children}
    </section>
  )
}

/** 键值字段表：label 左对齐固定宽度，value 自动换行。 */
export function FieldList({ rows }: { rows: { label: string; value: string }[] }) {
  if (!rows.length) return <Empty text="暂无" />
  return (
    <dl className="space-y-2.5 text-sm">
      {rows.map(r => (
        <div key={r.label} className="flex gap-3">
          <dt className="w-20 shrink-0 text-gray-400">{r.label}</dt>
          <dd className="flex-1 leading-relaxed text-gray-700">{r.value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** 小圆角标签。tone 控制配色。 */
export function Pill({
  children,
  tone = 'gray',
}: {
  children: ReactNode
  tone?: 'gray' | 'rose' | 'amber' | 'indigo' | 'emerald'
}) {
  const tones: Record<string, string> = {
    gray: 'bg-gray-100 text-gray-600',
    rose: 'bg-rose-50 text-rose-600',
    amber: 'bg-amber-50 text-amber-700',
    indigo: 'bg-indigo-50 text-indigo-600',
    emerald: 'bg-emerald-50 text-emerald-600',
  }
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

/** 空态占位。 */
export function Empty({ text = '暂无内容' }: { text?: string }) {
  return <p className="py-2 text-xs text-gray-400">{text}</p>
}

/** 大空态（整个分区为空时）。 */
export function SectionEmpty({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-gray-200 bg-white/60 py-16 text-center">
      <span className="text-gray-300">{icon}</span>
      <p className="text-sm text-gray-400">{text}</p>
    </div>
  )
}

/** 把任意值规整为可显示字符串（数组顿号连接，对象 JSON）。 */
export function fmtVal(v: unknown): string {
  if (v == null || v === '') return ''
  if (Array.isArray(v)) {
    return v.map(x => (typeof x === 'object' && x !== null ? JSON.stringify(x) : String(x))).join('、')
  }
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/** 按 label 映射从对象抽取非空字段为字段表行。 */
export function pickFields(
  data: Record<string, unknown> | null | undefined,
  labels: Record<string, string>,
): { label: string; value: string }[] {
  const d = data ?? {}
  return Object.entries(labels)
    .filter(([k]) => {
      const v = d[k]
      return v != null && v !== '' && !(Array.isArray(v) && v.length === 0)
    })
    .map(([k, label]) => ({ label, value: fmtVal(d[k]) }))
}
