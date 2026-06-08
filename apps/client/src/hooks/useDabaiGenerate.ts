/**
 * @file hooks/useDabaiGenerate.ts — 大白文生成 + 列表状态。
 * 支持 SSE 流式生成（边生成边落库 + 8 步进度）与非流式回退。
 * 组件只消费返回的状态与动作，不直接碰 fetch/axios。
 */
import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { dabaiApi, dabaiGenerateStream } from '../api/dabai'
import type {
  DabaiGenerateRequest,
  DabaiProjectDetail,
  DabaiProjectSummary,
} from '../types/dabai'

export type StepState = 'pending' | 'running' | 'done' | 'error'

interface UseDabaiGenerateResult {
  list: DabaiProjectSummary[]
  detail: DabaiProjectDetail | null
  generating: boolean
  steps: string[]
  stepStatus: Record<string, StepState>
  chapterTotal: number
  generate: (payload: DabaiGenerateRequest) => Promise<void>
  openDetail: (id: string) => Promise<void>
  remove: (id: string) => Promise<void>
}

function errMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (err instanceof Error) return err.message
  return fallback
}

export function useDabaiGenerate(): UseDabaiGenerateResult {
  const [list, setList] = useState<DabaiProjectSummary[]>([])
  const [detail, setDetail] = useState<DabaiProjectDetail | null>(null)
  const [generating, setGenerating] = useState(false)
  const [steps, setSteps] = useState<string[]>([])
  const [stepStatus, setStepStatus] = useState<Record<string, StepState>>({})
  const [chapterTotal, setChapterTotal] = useState(0)

  const refreshList = useCallback(async () => {
    try {
      const res = await dabaiApi.list()
      setList(res.data.items)
    } catch (err) {
      toast.error(errMessage(err, '加载列表失败'))
    }
  }, [])

  useEffect(() => { refreshList() }, [refreshList])

  const openDetail = useCallback(async (id: string) => {
    try {
      const res = await dabaiApi.get(id)
      setDetail(res.data)
    } catch (err) {
      toast.error(errMessage(err, '加载详情失败'))
    }
  }, [])

  const generate = useCallback(async (payload: DabaiGenerateRequest) => {
    setGenerating(true)
    setDetail(null)
    setSteps([])
    setStepStatus({})
    setChapterTotal(0)
    const mark = (step: string, s: StepState) =>
      setStepStatus((prev) => ({ ...prev, [step]: s }))
    try {
      await dabaiGenerateStream(payload, (ev) => {
        switch (ev.event) {
          case 'project_created':
            setSteps(ev.steps)
            setStepStatus(Object.fromEntries(ev.steps.map((s) => [s, 'pending'])))
            break
          case 'step_start': mark(ev.step, 'running'); break
          case 'step_done': mark(ev.step, 'done'); break
          case 'chapter_batch':
            mark('chapter_outlines', 'running')
            setChapterTotal(ev.total)
            break
          case 'step_error':
            mark(ev.step, 'error')
            toast.error(`${ev.step} 失败：${ev.message}`)
            break
          case 'done':
            openDetail(ev.project_id)
            refreshList()
            break
          case 'error':
            toast.error(ev.message)
            break
          default: break
        }
      })
    } catch (err) {
      toast.error(errMessage(err, '生成失败'))
    } finally {
      setGenerating(false)
    }
  }, [openDetail, refreshList])

  const remove = useCallback(async (id: string) => {
    try {
      await dabaiApi.remove(id)
      toast.success('已删除')
      setDetail((d) => (d?.id === id ? null : d))
      await refreshList()
    } catch (err) {
      toast.error(errMessage(err, '删除失败'))
    }
  }, [refreshList])

  return { list, detail, generating, steps, stepStatus, chapterTotal, generate, openDetail, remove }
}
