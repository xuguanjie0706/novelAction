/**
 * @file pages/DabaiPage.tsx — 大白文（爽点节拍器）独立入口页。
 * 流程：输入一句话创意 → 生成（走 /api/v1/dabai）→ 展示全链路产物 + 大白文 linter。
 * 与精品文创作流完全隔离；只读展示，不做逐字编辑。
 * 数据/动作来自 useDabaiGenerate；侧栏复用 HomeSidebar（新增 dabai 入口）。
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Flame, Loader2, Trash2, Wand2, X } from 'lucide-react'
import HomeSidebar from '../components/Home/HomeSidebar'
import HomeTopBar from '../components/Home/HomeTopBar'
import LlmAgentMenu from '../components/Layout/LlmAgentMenu'
import DabaiResult from '../components/Dabai/DabaiResult'
import DabaiWritePanel from '../components/Dabai/DabaiWritePanel'
import { useHomeSidebarNavigate } from '../hooks/useHomeSidebarNavigate'
import { useDabaiGenerate, type StepState } from '../hooks/useDabaiGenerate'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload, llmProviderIdFromRoute } from '../store'
import { DABAI_STEP_LABELS, type DabaiChapter } from '../types/dabai'

function StepDot({ state }: { state: StepState }) {
  if (state === 'done') return <Check size={14} className="text-emerald-500" />
  if (state === 'running') return <Loader2 size={14} className="animate-spin text-amber-500" />
  if (state === 'error') return <X size={14} className="text-rose-500" />
  return <span className="h-2 w-2 rounded-full bg-gray-300" />
}

export default function DabaiPage() {
  const navigate = useNavigate()
  const setCurrentProject = useAppStore((s) => s.setCurrentProject)
  const aiBackendRoute = useAppStore((s) => s.aiBackendRoute)
  const handleSidebarNavigate = useHomeSidebarNavigate({
    projects: [], activeId: 'dabai', navigate, setCurrentProject,
  })
  const { list, detail, generating, steps, stepStatus, chapterTotal, generate, openDetail, remove } =
    useDabaiGenerate()

  const [logline, setLogline] = useState('废柴少年觉醒吞噬系统，一路逆袭打脸天才')
  const [mock, setMock] = useState(false)
  const [volumeChapters, setVolumeChapters] = useState(30)
  const [writeChapter, setWriteChapter] = useState<DabaiChapter | null>(null)

  const onGenerate = () => {
    if (!logline.trim()) return
    generate({
      logline: logline.trim(), mock,
      model_profile: modelProfileFromRoute(aiBackendRoute),
      ...routeLlmProviderPayload(aiBackendRoute),
      volume_count: 6, volume_chapters: volumeChapters, big_beat_every: 5,
      chapter_batch_size: 30,
    })
  }

  return (
    <div className="min-h-screen bg-[#f8fafc] text-gray-950 lg:flex">
      <HomeSidebar todayWords={0} onNavigate={handleSidebarNavigate} activeId="dabai" />

      <div className="flex min-w-0 flex-1 flex-col">
        <HomeTopBar />
        <main className="min-w-0 flex-1 overflow-auto px-5 py-6 sm:px-8">
          <div className="mx-auto max-w-5xl space-y-5">
            {/* 头部 + 生成表单 */}
            <header className="rounded-2xl border border-amber-100 bg-white p-5 shadow-[0_10px_30px_rgba(245,158,11,0.08)]">
              <div className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
                <Flame size={14} />大白文工作台 · 爽点节拍器
              </div>
              <h1 className="mt-2 text-xl font-bold text-gray-900">一句话生成大白文</h1>
              <p className="mt-1 text-sm text-gray-500">
                独立链路：情绪势能 → 爽点引爆 → 即时反馈 → 强钩子。章纲无 choice_cost，质检走大白文专属规则。
              </p>

              <div className="mt-4 space-y-3">
                <textarea
                  value={logline}
                  onChange={(e) => setLogline(e.target.value)}
                  rows={2}
                  placeholder="输入一句话创意，例如：废柴少年觉醒吞噬系统，一路逆袭打脸天才"
                  className="w-full resize-none rounded-xl border border-gray-200 px-4 py-3 text-sm text-gray-800 outline-none focus:border-amber-300"
                />
                <div className="flex flex-wrap items-center gap-4">
                  {!mock && (
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <span className="text-gray-400">模型/线路</span>
                      <LlmAgentMenu />
                    </div>
                  )}
                  <label className="flex items-center gap-2 text-sm text-gray-600">
                    <input type="checkbox" checked={mock} onChange={(e) => setMock(e.target.checked)} />
                    离线 mock（勾选则不调真实 LLM；不勾走上方所选线路）
                  </label>
                  <label className="flex items-center gap-2 text-sm text-gray-600">
                    每卷章数
                    <input
                      type="number" min={5} max={120} value={volumeChapters}
                      onChange={(e) => setVolumeChapters(Number(e.target.value) || 30)}
                      className="w-20 rounded-lg border border-gray-200 px-2 py-1 text-sm"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={onGenerate}
                    disabled={generating}
                    className="ml-auto inline-flex items-center gap-2 rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-amber-600 disabled:opacity-60"
                  >
                    {generating ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
                    {generating ? '生成中…' : '生成'}
                  </button>
                </div>
              </div>
            </header>

            {/* 流式生成进度（8 步） */}
            {generating && steps.length > 0 && (
              <section className="rounded-2xl border border-amber-100 bg-white p-4 shadow-sm">
                <div className="mb-3 text-sm font-bold text-gray-900">生成进度（边生成边落库）</div>
                <ol className="flex flex-wrap gap-2">
                  {steps.map((s) => {
                    const st = stepStatus[s] ?? 'pending'
                    return (
                      <li
                        key={s}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                          st === 'done' ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                          : st === 'running' ? 'border-amber-200 bg-amber-50 text-amber-700'
                          : st === 'error' ? 'border-rose-200 bg-rose-50 text-rose-600'
                          : 'border-gray-200 bg-white text-gray-400'
                        }`}
                      >
                        <StepDot state={st} />
                        {DABAI_STEP_LABELS[s] ?? s}
                        {s === 'chapter_outlines' && chapterTotal > 0 && `（${chapterTotal}章）`}
                      </li>
                    )
                  })}
                </ol>
              </section>
            )}

            {/* 历史列表 */}
            {list.length > 0 && (
              <section className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
                <div className="mb-2 text-sm font-bold text-gray-900">历史作品（{list.length}）</div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {list.map((p) => (
                    <div
                      key={p.id}
                      className="flex items-center gap-2 rounded-xl border border-gray-100 px-3 py-2 hover:border-amber-200"
                    >
                      <button
                        type="button"
                        onClick={() => openDetail(p.id)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="truncate text-sm text-gray-800">{p.title || p.logline}</div>
                        <div className="text-xs text-gray-400">
                          {p.volume_count}卷 · {p.chapter_count}章 · 质检{p.linter_score ?? '-'}分
                          {p.mock && ' · mock'}
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => remove(p.id)}
                        className="rounded-lg p-1.5 text-gray-300 hover:bg-rose-50 hover:text-rose-500"
                        title="删除"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* 产物展示 */}
            {detail ? (
              <DabaiResult detail={detail} onWrite={setWriteChapter} />
            ) : (
              !generating && (
                <div className="rounded-2xl border border-dashed border-gray-200 bg-white/60 p-10 text-center text-sm text-gray-400">
                  输入一句话创意，点「生成」查看全链路产物与爽点节拍章纲
                </div>
              )
            )}
          </div>
        </main>
      </div>

      {detail && writeChapter && (
        <DabaiWritePanel
          projectId={detail.id}
          chapter={writeChapter}
          mock={mock}
          modelProfile={modelProfileFromRoute(aiBackendRoute)}
          llmProviderId={llmProviderIdFromRoute(aiBackendRoute)}
          onClose={() => setWriteChapter(null)}
          onSaved={() => openDetail(detail.id)}
        />
      )}
    </div>
  )
}
