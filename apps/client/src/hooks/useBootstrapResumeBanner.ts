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
import {
  gateResumeHint,
  isResumableFailedRun,
  pickResumableBootstrapRun,
} from '../utils/bootstrapResumable'

export interface BootstrapResumeSnapshot {
  runId: string
  logline: string
  status: string
  /** failed 但 gate_data 仍有效，可 POST resume 从闸门续跑 */
  resumableFailed?: boolean
  resumeHint?: string
}

export function useBootstrapResumeBanner(projectId?: string | null) {
  const [snapshot, setSnapshot] = useState<BootstrapResumeSnapshot | null>(null)

  const refresh = useCallback(async () => {
    try {
      if (projectId) {
        const res = await bootstrapRunsApi.listByProject(projectId)
        const row = pickResumableBootstrapRun(res.data)
        if (row) {
          const gd = row.gate_data
          const failedGate = isResumableFailedRun(row)
          const snap: BootstrapResumeSnapshot = {
            runId: row.run_id,
            logline: (row.logline || '').trim(),
            status: row.status,
            resumableFailed: failedGate,
            resumeHint: failedGate && gd && typeof gd === 'object'
              ? gateResumeHint(gd as Record<string, unknown>)
              : undefined,
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
      let r
      try {
        const res = await bootstrapRunsApi.get(stored.runId)
        r = res.data
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 404) clearActiveBootstrapRun()
        setSnapshot(null)
        return
      }
      if (r.status === 'done' || r.status === 'cancelled') {
        clearActiveBootstrapRun()
        setSnapshot(null)
        return
      }
      if (r.status === 'failed' && !isResumableFailedRun(r)) {
        clearActiveBootstrapRun()
        setSnapshot(null)
        return
      }
      const gd = r.gate_data
      const failedGate = r.status === 'failed' && isResumableFailedRun(r)
      setSnapshot({
        runId: r.run_id,
        logline: ((r.logline ?? stored.logline) || '').trim(),
        status: r.status,
        resumableFailed: failedGate,
        resumeHint: failedGate && gd && typeof gd === 'object'
          ? gateResumeHint(gd as Record<string, unknown>)
          : undefined,
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
