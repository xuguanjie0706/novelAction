/**
 * 故事线详情内：织网矩阵摘要 + 跳转织网页
 */
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { GitBranch } from 'lucide-react'
import type { StoryLine } from '../../../types'
import { hasStorylineWeave } from '../../../utils/storylineWeaveUtils'

export default function StorylineWeaveSummary({
  projectId,
  storyline,
}: {
  projectId: string
  storyline: StoryLine
}) {
  if (!hasStorylineWeave(storyline)) {
    return (
      <p className="text-xs text-gray-500">
        暂无织网数据（需完成 Bootstrap 故事线 Step 4 织网矩阵）。
      </p>
    )
  }

  const extra = storyline.extra || {}
  const beats = (extra.volume_beats || []) as Array<{
    vol_index?: number
    beat?: string
    tension?: number
    is_active?: boolean
  }>
  const weight = extra.weight as number | undefined

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-gray-600">织网导演单</span>
        <Link
          to={`/project/${projectId}/storyweave`}
          className="text-xs text-indigo-600 hover:underline flex items-center gap-1"
        >
          <GitBranch size={12} />
          打开织网图
        </Link>
      </div>
      {weight != null && (
        <p className="text-xs text-gray-500">全书戏份权重：{(weight * 100).toFixed(0)}%</p>
      )}
      <div className="space-y-1 max-h-48 overflow-y-auto">
        {beats.map(b => (
          <div
            key={b.vol_index}
            className={clsx(
              'text-xs rounded border px-2 py-1',
              b.is_active === false ? 'bg-gray-50 text-gray-400' : 'bg-white text-gray-700',
            )}
          >
            <span className="font-medium">第{(b.vol_index ?? 0) + 1}卷</span>
            {b.is_active === false ? '（休眠）' : ` · ${(b.beat || '').slice(0, 40)} · 张力 ${b.tension ?? '—'}`}
          </div>
        ))}
      </div>
    </div>
  )
}
