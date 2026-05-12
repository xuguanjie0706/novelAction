/**
 * 检测是否有未结束的 Bootstrap 串行任务，用于首页 / 书架 / 小说详情顶部「继续生成」条。
 *
 * - 若提供 ``projectId``：优先读该项目下最近的 running / awaiting_gate run
 * - 否则读 ``sessionStorage`` 中的 run_id 并 GET 校验
 */
import { useCallback, useEffect, useState } from 'react'
import { bootstrapRunsApi } from '../api/client'
import {
  clearActiveBootstrapRun,
  readActiveBootstrapRun,
  saveActiveBootstrapRun,
} from '../utils/bootstrapActiveRun'

export interface BootstrapResumeSnapshot {
  runId: string
  logline: string
  status: string
}

export function useBootstrapResumeBanner(projectId?: string | null) {
  const [snapshot, setSnapshot] = useState<BootstrapResumeSnapshot | null>(null)

  const refresh = useCallback(async () => {
    try {
      if (projectId) {
        const res = await bootstrapRunsApi.listByProject(projectId)
        const row = res.data.find(r => r.status === 'running' || r.status === 'awaiting_gate')
        if (row) {
          const snap: BootstrapResumeSnapshot = {
            runId: row.run_id,
            logline: (row.logline || '').trim(),
            status: row.status,
          }
          setSnapshot(snap)
          saveActiveBootstrapRun({
            runId: row.run_id,
            logline: snap.logline || undefined,
            projectId,
          })
          return
        }
      }
      const stored = readActiveBootstrapRun()
      if (!stored?.runId) {
        setSnapshot(null)
        return
      }
      const res = await bootstrapRunsApi.get(stored.runId)
      const r = res.data
      if (r.status === 'done' || r.status === 'failed' || r.status === 'cancelled') {
        clearActiveBootstrapRun()
        setSnapshot(null)
        return
      }
      setSnapshot({
        runId: r.run_id,
        logline: ((r.logline ?? stored.logline) || '').trim(),
        status: r.status,
      })
    } catch {
      setSnapshot(null)
    }
  }, [projectId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { snapshot, refresh }
}
