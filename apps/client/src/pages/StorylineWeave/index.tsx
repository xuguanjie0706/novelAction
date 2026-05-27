/**
 * StorylineWeave — 故事线织网图（计划 vs 实际）
 */
import { RefreshCw, GitBranch } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useStorylineWeaveData } from './useStorylineWeaveData'
import WeaveMatrixView from './WeaveMatrixView'

export default function StorylineWeavePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = projectId || ''
  const { data, loading, error, refresh } = useStorylineWeaveData(pid)

  const hasWeave = data?.storylines?.some(
    s => s.volume_cells?.some(c => (c.planned_tension ?? 0) > 0 || c.beat),
  )

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-semibold text-novel-ink flex items-center gap-2">
          <GitBranch size={20} className="text-indigo-600" />
          故事线织网
        </h1>
        <button
          type="button"
          onClick={() => refresh()}
          disabled={loading}
          className="text-xs px-3 py-1.5 rounded-lg border border-novel-border hover:bg-novel-panel flex items-center gap-1"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {loading && <p className="text-sm text-novel-ink-muted">加载织网数据…</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {!loading && !error && data && !hasWeave && (
        <p className="text-sm text-novel-ink-muted">
          尚未生成织网数据。请完成 Bootstrap「故事线」步骤（Step 4 织网矩阵）后查看。
        </p>
      )}
      {!loading && data && hasWeave && <WeaveMatrixView data={data} />}
    </div>
  )
}
