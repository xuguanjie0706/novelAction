/**
 * @file 全量生成大纲配置弹窗
 */
import { useState } from 'react'
import { BookOpen, Sparkles, X } from 'lucide-react'
import clsx from 'clsx'
import { projectsApi } from '../../api/client'
import { useAppStore, toOutlineApiModelProfile, routeLlmProviderPayload } from '../../store'
import { TargetWordsInput } from '../../components/TargetWordsInput'

const OUTLINE_WORD_OPTIONS = [
  { label: '短篇', value: 800000 },
  { label: '标准', value: 1200000 },
  { label: '长篇', value: 1500000 },
  { label: '超长篇', value: 2000000 },
] as const

export default function FullGenConfigModal({
  projectId: _projectId,
  hasExistingOutline,
  onClose,
  onDispatch,
}: {
  projectId: string
  hasExistingOutline: boolean
  onClose: () => void
  onDispatch: (params: {
    scale_hint: string
    theme_statement?: string
    model_profile: string
    clear_existing: boolean
    llm_provider_id?: string
  }) => void
}) {
  const { currentProject, setCurrentProject } = useAppStore()
  const initWords = Number(currentProject?.target_words) || 1200000
  const [targetWords, setTargetWords] = useState(initWords)
  const [customMode, setCustomMode] = useState(false)
  const [themeStatement, setThemeStatement] = useState('')
  const [clearExisting, setClearExisting] = useState(hasExistingOutline)
  const [saving, setSaving] = useState(false)

  const estChapters = Math.round(targetWords / 2300)
  const estVols = Math.ceil(estChapters / 60)

  const toScaleHint = (w: number) => {
    if (w <= 500000) return 'micro'
    if (w <= 900000) return 'short'
    if (w <= 1400000) return 'medium'
    if (w <= 1700000) return 'long'
    return 'epic'
  }

  const handleStart = async () => {
    if (clearExisting && !window.confirm('将清除现有全部大纲节点，确定继续？')) return
    if (targetWords !== initWords && currentProject) {
      setSaving(true)
      try {
        const res = await projectsApi.update(currentProject.id, { target_words: targetWords })
        setCurrentProject(res.data)
      } catch {
        /* 静默：后端仍用传入 scale */
      } finally {
        setSaving(false)
      }
    }
    const route = useAppStore.getState().aiBackendRoute
    onDispatch({
      scale_hint: toScaleHint(targetWords),
      theme_statement: themeStatement.trim() || undefined,
      model_profile: toOutlineApiModelProfile(route),
      clear_existing: clearExisting,
      ...routeLlmProviderPayload(route),
    })
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
          <BookOpen size={18} className="text-amber-500" />
          <h3 className="font-semibold text-gray-800 flex-1">全量生成大纲</h3>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={16} />
          </button>
        </div>
        <div className="px-5 py-4 space-y-4">
          <p className="text-xs text-gray-500 leading-relaxed">
            AI 读取项目的 logline、类型、世界观、人物生成大纲；后端会按字数目标推算卷数并写入大纲树。
            <span className="block mt-1 text-amber-600 font-medium">任务将在右下角队列中后台运行。</span>
          </p>
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-gray-500">全书字数目标</label>
              <button type="button" onClick={() => setCustomMode(m => !m)} className="text-xs text-amber-500 hover:text-amber-600">
                {customMode ? '快捷选择' : '自定义'}
              </button>
            </div>
            {customMode ? (
              <TargetWordsInput value={targetWords} onChange={setTargetWords} />
            ) : (
              <div className="grid grid-cols-4 gap-1.5">
                {OUTLINE_WORD_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setTargetWords(opt.value)}
                    className={clsx(
                      'rounded-xl border py-2 text-center transition-all',
                      targetWords === opt.value
                        ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-300'
                        : 'border-gray-200 hover:border-gray-300 bg-white',
                    )}
                  >
                    <div className={clsx('text-xs font-medium', targetWords === opt.value ? 'text-indigo-700' : 'text-gray-700')}>
                      {opt.label}
                    </div>
                    <div className="text-[10px] text-gray-400 mt-0.5">{(opt.value / 10000).toFixed(0)}万字</div>
                  </button>
                ))}
              </div>
            )}
            <div className="mt-2 rounded-lg bg-amber-50 border border-amber-100 px-3 py-2 text-xs text-amber-700">
              约 <span className="font-semibold">{estChapters}</span> 章 · 约 <span className="font-semibold">{estVols}</span> 卷
              {targetWords !== initWords && <span className="ml-2 text-amber-500">（修改后将保存到项目）</span>}
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-2">全书立意</label>
            <textarea
              value={themeStatement}
              onChange={e => setThemeStatement(e.target.value)}
              placeholder="例如：人在被命运压低时，仍能靠选择重塑自身价值。"
              className="w-full min-h-[64px] text-sm border border-gray-200 rounded-xl px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-amber-300"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-gray-100 bg-gray-50">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-gray-500 border border-gray-200 rounded-lg bg-white">
            取消
          </button>
          <button
            type="button"
            onClick={handleStart}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-1.5 text-sm font-medium bg-amber-500 text-white rounded-lg disabled:opacity-50"
          >
            <Sparkles size={14} />
            {saving ? '保存中...' : '加入队列并开始'}
          </button>
        </div>
      </div>
    </div>
  )
}
