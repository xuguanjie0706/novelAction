/**
 * @file useVolumeExpand — write-dabailab 侧栏「按卷展开章纲」状态机。
 * 同一时刻只允许展开一卷；SSE 批进度写入 progress；done 后回调 onDone（重拉详情）。
 */
import { useCallback, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { dabaiExpandVolumeStream } from '../../../../api/dabai'
import type { DabaiVolume } from '../../../../types/dabai'

export interface VolumeExpandState {
  /** 正在展开的卷 id（null=空闲）。 */
  expandingId: string | null
  /** 进度文案，如「12/30 章」。 */
  progress: string
  /** 触发展开；运行中重复点击被忽略。 */
  expand: (volume: DabaiVolume) => void
}

export function useVolumeExpand(projectId: string, onDone: () => void): VolumeExpandState {
  const [expandingId, setExpandingId] = useState<string | null>(null)
  const [progress, setProgress] = useState('')
  const runningRef = useRef(false)

  const expand = useCallback((volume: DabaiVolume) => {
    if (runningRef.current || !volume.id) return
    runningRef.current = true
    setExpandingId(volume.id)
    setProgress('')
    let failed = false
    dabaiExpandVolumeStream(projectId, volume.id, {}, ev => {
      if (ev.event === 'chapter_batch') {
        setProgress(`${ev.total} 章`)
      } else if (ev.event === 'linter_done') {
        const score = ev.score ?? '—'
        const issues = ev.issue_count ?? 0
        if (ev.status === 'blocked') {
          toast.error(`卷纲质检阻断：${score} 分，${issues} 项问题（含 critical）`)
        } else if (ev.status === 'warning') {
          toast(`卷纲质检：${score} 分，${issues} 项警告`, { icon: '⚠️' })
        } else {
          toast.success(`卷纲质检：${score} 分通过`)
        }
      } else if (ev.event === 'done') {
        toast.success(`第 ${ev.volume_number} 卷章纲已展开（${ev.created} 章）`)
      } else if (ev.event === 'error') {
        failed = true
        toast.error(ev.message || '展开失败')
      }
    })
      .catch(() => { failed = true; toast.error('展开请求失败') })
      .finally(() => {
        runningRef.current = false
        setExpandingId(null)
        setProgress('')
        if (!failed) onDone()
      })
  }, [projectId, onDone])

  return { expandingId, progress, expand }
}
