/**
 * WritingConfigPanel — 写作质量门控配置面板
 *
 * 读取 /projects/{id}/writing-config，展示可调节的门控参数。
 * 每个参数独立保存（失焦或直接点击时 PATCH）。
 *
 * 写配置保存后同步更新 store，确保 ChapterEditor 的 writingConfig 是最新值。
 */
import React, { useEffect, useState } from 'react'
import { Loader2, Target } from 'lucide-react'
import toast from 'react-hot-toast'
import { projectsApi, type WritingConfig } from '../../api/client'
import { useAppStore } from '../../store'

export default function WritingConfigPanel({ projectId }: { projectId: string }) {
  const [cfg, setCfg] = useState<WritingConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const currentProject = useAppStore(s => s.currentProject)
  const setCurrentProject = useAppStore(s => s.setCurrentProject)

  useEffect(() => {
    projectsApi.getWritingConfig(projectId)
      .then(res => setCfg(res.data.writing_config))
      .catch(() => { /* 静默失败，不影响主页渲染 */ })
  }, [projectId])

  const save = async (patch: Partial<typeof cfg>) => {
    if (!cfg) return
    const next = { ...cfg, ...patch }
    setCfg(next)
    setSaving(true)
    try {
      const res = await projectsApi.updateWritingConfig(projectId, patch as any)
      if (currentProject) {
        setCurrentProject({
          ...currentProject,
          extra: {
            ...((currentProject.extra as Record<string, unknown>) ?? {}),
            writing_config: res.data.writing_config,
          } as typeof currentProject.extra,
        })
      }
    } catch {
      toast.error('保存写作配置失败')
    } finally {
      setSaving(false)
    }
  }

  if (!cfg) return null

  return (
    <section className="mt-8">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-gray-900">
        <Target size={18} className="text-amber-400" />
        写作质量门控
        {saving && <Loader2 size={14} className="ml-1 animate-spin text-gray-400" />}
      </h2>
      <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm space-y-5">
        {/* 开关 */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-800">启用质量门控循环</p>
            <p className="mt-0.5 text-xs text-gray-500">
              开启后，空章点「生成」与「重写本章」会走门控流：自动质检，未达标按策略重写，最多 {cfg.max_rewrite_attempts} 次。
              已有正文时「生成」为续写追加，仅单次质检、不循环重写。队列里出现「门控配置」「第 N 轮」「qc_result」即已生效。
            </p>
          </div>
          <button
            type="button"
            onClick={() => save({ auto_quality_gate: !cfg.auto_quality_gate })}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
              cfg.auto_quality_gate ? 'bg-amber-400' : 'bg-gray-200'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                cfg.auto_quality_gate ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>

        {cfg.auto_quality_gate && (
          <>
            {/* 综合分 */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-gray-700">综合质检分下限</label>
                <span className="text-sm font-semibold text-amber-600 w-8 text-right">
                  {cfg.min_overall_score.toFixed(1)}
                </span>
              </div>
              <input
                type="range" min="0" max="10" step="0.5"
                value={cfg.min_overall_score}
                onChange={e => setCfg(c => c ? { ...c, min_overall_score: parseFloat(e.target.value) } : c)}
                onMouseUp={e => save({ min_overall_score: parseFloat((e.target as HTMLInputElement).value) })}
                onTouchEnd={e => save({ min_overall_score: parseFloat((e.target as HTMLInputElement).value) })}
                className="w-full accent-amber-400"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                <span>0 宽松</span>
                <span className="text-gray-500">建议 6.0–7.5</span>
                <span>10 严格</span>
              </div>
            </div>

            {/* 订阅意愿分 */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-gray-700">章末订阅意愿分下限</label>
                <span className="text-sm font-semibold text-amber-600 w-8 text-right">
                  {cfg.min_subscribe_intent.toFixed(1)}
                </span>
              </div>
              <input
                type="range" min="0" max="10" step="0.5"
                value={cfg.min_subscribe_intent}
                onChange={e => setCfg(c => c ? { ...c, min_subscribe_intent: parseFloat(e.target.value) } : c)}
                onMouseUp={e => save({ min_subscribe_intent: parseFloat((e.target as HTMLInputElement).value) })}
                onTouchEnd={e => save({ min_subscribe_intent: parseFloat((e.target as HTMLInputElement).value) })}
                className="w-full accent-amber-400"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                <span>0 宽松</span>
                <span className="text-gray-500">独立门槛（章末钩子）</span>
                <span>10 严格</span>
              </div>
            </div>

            {/* 最大重写次数 */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-gray-700">最大重写次数</label>
                <span className="text-sm font-semibold text-amber-600">{cfg.max_rewrite_attempts} 次</span>
              </div>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map(n => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => save({ max_rewrite_attempts: n })}
                    className={`flex-1 rounded-lg border py-1.5 text-sm font-medium transition-colors ${
                      cfg.max_rewrite_attempts === n
                        ? 'border-amber-400 bg-amber-50 text-amber-700'
                        : 'border-gray-200 text-gray-500 hover:border-gray-300'
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-xs text-gray-400">
                第1次：初稿 · 第2次：定点修复 · 第3次及以上：全量重写。超出次数后章节置为「待审阅」。
              </p>
            </div>

            {/* 分隔线 */}
            <div className="border-t border-gray-100 pt-1" />

            {/* 写前预警开关 */}
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-800 flex items-center gap-1.5">
                  写前预警
                  <span className="text-[10px] font-normal px-1.5 py-0.5 rounded bg-rose-50 text-rose-600 border border-rose-200">
                    实验性
                  </span>
                </p>
                <p className="mt-0.5 text-xs text-gray-500 leading-relaxed">
                  开启后，每次 AI 生成本章正文前自动生成写前简报（主角状态锁定、开篇/冲突/钩子写法、必发事件、幻觉预防），
                  <strong className="font-medium text-gray-700">优先注入写章 prompt 约束正文</strong>；侧栏可查阅同一份记录。
                </p>
                <p className="mt-1 text-xs text-amber-600">
                  ⚠️ 会额外消耗一次 AI 调用，小模型/本地模型效果有限，推荐配合 Gemini 线路使用。
                </p>
              </div>
              <button
                type="button"
                onClick={() => save({ pre_write_warning_enabled: !cfg.pre_write_warning_enabled })}
                className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none ${
                  cfg.pre_write_warning_enabled ? 'bg-rose-400' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                    cfg.pre_write_warning_enabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
