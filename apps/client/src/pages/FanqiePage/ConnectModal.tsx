/**
 * ConnectModal — 番茄凭据配置弹窗
 *
 * 未配置时由占位书架点击唤起；已配置时可通过「重新连接」打开。
 */
import React, { useEffect, useState } from 'react'
import { Flame, KeyRound, X } from 'lucide-react'
import type { FanqieConfig, FanqieConfigSummary } from '../../api/fanqieApi'

interface Props {
  open: boolean
  summary: FanqieConfigSummary | null
  onClose: () => void
  onSave: (cfg: FanqieConfig) => Promise<void>
}

const STEPS = [
  '登录 fanqienovel.com 作家专区',
  '打开 DevTools → Network',
  '刷新页面，找到 /api/author/book/ 请求',
  '右键 Copy as cURL，整段粘贴到下方',
]

export default function ConnectModal({ open, summary, onClose, onSave }: Props) {
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState<FanqieConfig>({
    cookies: '',
    csrf_token: '',
    ms_token: '',
    author_id: '',
  })

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !saving) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, saving, onClose])

  if (!open) return null

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.cookies.trim()) return
    setSaving(true)
    try {
      await onSave(form)
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="fanqie-connect-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={() => !saving && onClose()}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-gray-100 bg-white shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-gray-100 px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-50">
              <Flame size={20} className="text-red-500" fill="currentColor" />
            </div>
            <div>
              <h2 id="fanqie-connect-title" className="text-base font-bold text-gray-900">
                连接番茄作家后台
              </h2>
              <p className="mt-0.5 text-xs text-gray-400">
                {summary?.configured ? '更新凭据后重新同步书单' : '配置后即可同步番茄作品列表'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          <ol className="space-y-2 rounded-xl bg-gray-50 px-4 py-3 text-xs leading-relaxed text-gray-600">
            {STEPS.map((step, i) => (
              <li key={step} className="flex gap-2">
                <span className="shrink-0 font-semibold text-amber-500">{i + 1}.</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>

          <div>
            <label className="mb-1 flex items-center gap-1.5 text-xs font-medium text-gray-700">
              <KeyRound size={13} className="text-amber-500" />
              Cookie / cURL
            </label>
            <textarea
              value={form.cookies}
              onChange={e => setForm(f => ({ ...f, cookies: e.target.value }))}
              rows={5}
              placeholder="curl 'https://fanqienovel.com/api/author/book/book_list/v0?...' -b 'novel_web_id=...; sessionid=...' ..."
              className="w-full resize-none rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-xs font-mono text-gray-800 placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-amber-400"
              required
              autoFocus
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">作者 ID（可选）</label>
              <input
                value={form.author_id}
                onChange={e => setForm(f => ({ ...f, author_id: e.target.value }))}
                placeholder="从作家 URL 提取"
                className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-800 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">csrf-token（可选）</label>
              <input
                value={form.csrf_token}
                onChange={e => setForm(f => ({ ...f, csrf_token: e.target.value }))}
                placeholder="0001000000…"
                className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-800 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </div>
          </div>

          <div className="flex items-center justify-between gap-3 pt-1">
            <p className="text-[11px] text-gray-400">Cookie 约 60 天有效，失效后重新粘贴即可</p>
            <button
              type="submit"
              disabled={saving || !form.cookies.trim()}
              className="shrink-0 rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? '连接中…' : '保存并同步'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
