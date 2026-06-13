/**
 * 按要素生成/重写启动弹窗 — 可选作者写作指令；重写时可勾选写前/写后步骤。
 */
import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { Sparkles, X } from 'lucide-react'

export interface DraftLaunchOptions {
  userInstruction: string
  rerunPreWarn: boolean
  rerunScenePlan: boolean
  rerunQuality: boolean
  rerunDebrief: boolean
}

export const REWRITE_LAUNCH_DEFAULTS: DraftLaunchOptions = {
  userInstruction: '',
  rerunPreWarn: false,
  rerunScenePlan: false,
  rerunQuality: true,
  rerunDebrief: true,
}

interface Props {
  open: boolean
  mode: 'generate' | 'rewrite'
  /** 打开弹窗时预填写作指令（如质检「填入重写」）。 */
  initialInstruction?: string
  onClose: () => void
  onConfirm: (opts: DraftLaunchOptions) => void
}

const STEP_CHECKS: {
  key: keyof Pick<DraftLaunchOptions, 'rerunPreWarn' | 'rerunScenePlan' | 'rerunQuality' | 'rerunDebrief'>
  label: string
  hint: string
}[] = [
  { key: 'rerunPreWarn', label: '重新预警（导演单）', hint: '裁决章纲 vs 已写事实' },
  { key: 'rerunScenePlan', label: '重新分场', hint: '五拍拆 2-4 场调度' },
  { key: 'rerunQuality', label: '重新质检', hint: '衔接 / 五拍 / 钩子' },
  { key: 'rerunDebrief', label: '重新总结（复盘）', hint: '记忆与线索提取' },
]

export default function DraftLaunchModal({
  open, mode, initialInstruction, onClose, onConfirm,
}: Props) {
  const [opts, setOpts] = useState<DraftLaunchOptions>(REWRITE_LAUNCH_DEFAULTS)

  useEffect(() => {
    if (open) {
      setOpts({
        ...REWRITE_LAUNCH_DEFAULTS,
        userInstruction: initialInstruction?.trim() ?? '',
      })
    }
  }, [open, mode, initialInstruction])

  if (!open) return null

  const isRewrite = mode === 'rewrite'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl bg-white shadow-xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
            <Sparkles size={16} className="text-rose-500" />
            {isRewrite ? '按要素重写' : '按要素生成'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 px-4 py-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-gray-700">
              写作指令
              <span className="ml-1 font-normal text-gray-400">（可选，优先级最高）</span>
            </label>
            <textarea
              value={opts.userInstruction}
              onChange={e => setOpts(o => ({ ...o, userInstruction: e.target.value }))}
              placeholder="例如：开篇从对话切入；少写环境；加强见证者反应；某角色口吻更痞…"
              rows={4}
              className="w-full resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-800 placeholder:text-gray-400 focus:border-rose-300 focus:outline-none focus:ring-1 focus:ring-rose-200"
            />
          </div>

          {isRewrite ? (
            <div>
              <p className="mb-2 text-xs font-medium text-gray-700">写前 / 写后步骤</p>
              <div className="space-y-2">
                {STEP_CHECKS.map(({ key, label, hint }) => (
                  <label
                    key={key}
                    className="flex cursor-pointer items-start gap-2 rounded-lg border border-gray-100 px-3 py-2 hover:bg-gray-50"
                  >
                    <input
                      type="checkbox"
                      checked={opts[key]}
                      onChange={e => setOpts(o => ({ ...o, [key]: e.target.checked }))}
                      className="mt-0.5 rounded border-gray-300 text-rose-500 focus:ring-rose-300"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-medium text-gray-800">{label}</span>
                      <span className="block text-[10px] text-gray-400">{hint}</span>
                    </span>
                  </label>
                ))}
              </div>
              <p className="mt-2 text-[10px] text-gray-400">
                未勾选的预警/分场将复用侧栏已有记录；正文始终重写。
              </p>
            </div>
          ) : (
            <p className="text-[11px] text-gray-400">
              首次生成将自动跑预警 → 分场 → 正文，写后默认质检与复盘。
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-gray-100 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => onConfirm(opts)}
            className={clsx(
              'rounded-lg px-4 py-1.5 text-xs font-semibold text-white',
              'bg-rose-500 hover:bg-rose-600',
            )}
          >
            {isRewrite ? '开始重写' : '开始生成'}
          </button>
        </div>
      </div>
    </div>
  )
}
