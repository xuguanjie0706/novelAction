/**
 * @file useBootstrapStepData — 步骤完成后自动拉取对应 API 数据
 *
 * 职责：监听 `steps` 列表，当某步变为 `done` 且存在 `projectId` 时，
 * 调用对应 API 拉取真实数据，返回 `stepData` map 供右侧详情面板渲染。
 *
 * 设计原则：
 * - 幂等：同一步骤只拉一次（fetchedRef 记录已触发的 key）
 * - 静默失败：拉取出错不抛出，仅返回 null（Detail 面板降级为"X 条"）
 * - projectId 变化时完整重置（用于新建流程覆盖旧数据）
 */
import { useEffect, useRef, useState } from 'react'
import type { StepKey, StepState } from './useBootstrapStream'
import {
  projectsApi,
  powerSystemsApi,
  factionsApi,
  storylinesApi,
  charactersApi,
  skillsApi,
  itemsApi,
  settingsApi,
  outlineApi,
} from '../../../api/client'

export type StepDataMap = Partial<Record<StepKey, unknown>>

/**
 * 根据 steps 中已完成步骤自动拉取对应 API 数据。
 *
 * @param steps - Bootstrap 步骤列表（来自 useBootstrapStream）
 * @param projectId - 生成成功后的项目 ID；为 null 时不触发任何请求
 * @returns stepData map，key 为 StepKey，value 为对应 API 返回的原始数据
 */
export function useBootstrapStepData(
  steps: StepState[],
  projectId: string | null,
): StepDataMap {
  const [dataMap, setDataMap] = useState<StepDataMap>({})
  /** 已发出请求的步骤集合，防止重复拉取 */
  const fetchedRef = useRef<Set<StepKey>>(new Set())

  // projectId 变化时重置（新生成流程）
  useEffect(() => {
    setDataMap({})
    fetchedRef.current.clear()
  }, [projectId])

  useEffect(() => {
    if (!projectId) return

    for (const step of steps) {
      if (step.status !== 'done') continue
      if (fetchedRef.current.has(step.key)) continue
      fetchedRef.current.add(step.key)

      void fetchStepData(step.key, projectId).then(data => {
        if (data !== null) {
          setDataMap(prev => ({ ...prev, [step.key]: data }))
        }
      })
    }
  }, [steps, projectId])

  return dataMap
}

// ── 各步骤数据拉取 ────────────────────────────────────────────────────────────

/**
 * 按步骤 key 调用对应 API，返回原始数据或 null（失败时静默降级）。
 */
async function fetchStepData(key: StepKey, pid: string): Promise<unknown> {
  try {
    switch (key) {
      case 'project':
        return (await projectsApi.get(pid)).data

      case 'power_systems':
        return (await powerSystemsApi.list(pid)).data

      case 'factions':
        return (await factionsApi.list(pid)).data

      case 'storylines':
        return (await storylinesApi.list(pid)).data

      case 'characters':
        return (await charactersApi.list(pid)).data

      case 'skills':
        return (await skillsApi.list(pid)).data

      case 'items':
        return (await itemsApi.list(pid)).data

      case 'settings':
        return (await settingsApi.list(pid)).data

      case 'relations':
        return (await charactersApi.listRelationships(pid)).data

      case 'volumes': {
        const tree = (await outlineApi.getTree(pid)).data as any[]
        // 只返回 volume 层节点，不含子节点，减少数据量
        return Array.isArray(tree)
          ? tree.filter((n: any) => n.node_type === 'volume' || !n.node_type)
          : tree
      }

      // 以下步骤已有专属展示渠道（positioningData / insights）或无需额外拉取
      case 'positioning':
      case 'opening_contract':
      case 'consistency':
      case 'memory':
      case 'all':
      case 'saving':
      default:
        return null
    }
  } catch {
    // 静默失败，Detail 面板降级为"X 条"摘要
    return null
  }
}

