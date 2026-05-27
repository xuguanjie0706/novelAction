/**
 * @file BookshelfDetailPage — 项目生成纪要详情页
 *
 * 职责：
 * - 从后端并行拉取项目所有生成数据（人物、势力、设定等）
 * - 渲染左侧分区导航（13 个区域，带条目数 badge）
 * - 右侧渲染 SectionContent 对应区域的富内容
 * - 提供「返回书架」「进入工作台」与未结束 Bootstrap 的「继续生成」
 *
 * 路由：/bookshelf/:projectId/recap（从书架「小说详情」页的「结构化纪要」进入）
 *
 * 数据来源：所有字段均来自数据库 API，不依赖 SSE 临时内存。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  BookOpen, Layers, Users, Zap, Sword, Package,
  Map, BookMarked, CheckSquare, GitBranch, Loader2, AlertCircle,
  Castle, HeartPulse, Swords,
} from 'lucide-react'
import toast from 'react-hot-toast'
import GenerateWizard from '../components/Bootstrap/GenerateWizard'
import ActiveBootstrapResumeBar from '../components/Bootstrap/ActiveBootstrapResumeBar'
import { useBootstrapResumeBanner } from '../hooks/useBootstrapResumeBanner'
import {
  projectsApi, charactersApi, factionsApi, powerSystemsApi,
  skillsApi, itemsApi, storylinesApi, settingsApi, outlineApi,
  bootstrapRunsApi,
} from '../api/client'
import { clearActiveBootstrapRun } from '../utils/bootstrapActiveRun'
import type { OutlineNode } from '../types'
import SectionContent, { type DetailData } from '../components/BookshelfDetail/SectionContent'
import RecapPageHeader from './BookshelfDetail/RecapPageHeader'
import { countOpeningContractEntries, resolveOpeningContract } from '../utils/openingContractDisplay'
import { resolveEmotionArc, resolveVillainArc } from '../utils/narrativeArcDisplay'

// ── 分区配置 ─────────────────────────────────────────────────

/**
 * 11 个可选内容区域的静态元数据。
 * count 由父组件在数据加载后填入。
 */
interface SectionCfg {
  id: string
  label: string
  icon: React.ReactNode
  color: string
  /** 从 DetailData 中计算条目数的函数 */
  countFn: (d: DetailData) => number
}

const SECTIONS: SectionCfg[] = [
  {
    id: 'overview',
    label: '立项概览',
    icon: <BookOpen size={16} />,
    color: '#f59e0b',
    countFn: () => 1,
  },
  {
    id: 'power',
    label: '境界体系',
    icon: <Zap size={16} />,
    color: '#06b6d4',
    countFn: d => d.powerSystems.length,
  },
  {
    id: 'factions',
    label: '势力组织',
    icon: <Castle size={16} />,
    color: '#a78bfa',
    countFn: d => d.factions.length,
  },
  {
    id: 'storylines',
    label: '故事线',
    icon: <GitBranch size={16} />,
    color: '#8b5cf6',
    countFn: d => d.storylines.length,
  },
  {
    id: 'characters',
    label: '人物',
    icon: <Users size={16} />,
    color: '#22c55e',
    countFn: d => d.characters.length,
  },
  {
    id: 'skills',
    label: '技能功法',
    icon: <Sword size={16} />,
    color: '#ef4444',
    countFn: d => d.skills.length,
  },
  {
    id: 'items',
    label: '道具法宝',
    icon: <Package size={16} />,
    color: '#eab308',
    countFn: d => d.items.length,
  },
  {
    id: 'settings',
    label: '叙事设定',
    icon: <Map size={16} />,
    color: '#06b6d4',
    countFn: d => d.settings.length,
  },
  {
    id: 'volumes',
    label: '卷级骨架',
    icon: <Layers size={16} />,
    color: '#f97316',
    countFn: d => d.volumes.length,
  },
  {
    id: 'emotion_arc',
    label: '情绪节律',
    icon: <HeartPulse size={16} />,
    color: '#ec4899',
    countFn: d => resolveEmotionArc(d.project.extra).length,
  },
  {
    id: 'villain_arc',
    label: '反派行动线',
    icon: <Swords size={16} />,
    color: '#ef4444',
    countFn: d => resolveVillainArc(d.project.extra).length,
  },
  {
    id: 'contract',
    label: '开局承诺',
    icon: <BookMarked size={16} />,
    color: '#22c55e',
    countFn: d => countOpeningContractEntries(
      resolveOpeningContract(d.insights, d.project.extra),
    ),
  },
  {
    id: 'consistency',
    label: '一致性扫描',
    icon: <CheckSquare size={16} />,
    color: '#ef4444',
    countFn: d => d.insights.consistency_issues?.length ?? 0,
  },
]

// ── 子组件：左侧导航项 ────────────────────────────────────────

interface NavItemProps {
  cfg: SectionCfg
  count: number
  isSelected: boolean
  onClick: () => void
}

/**
 * 左侧深棕导航中的单个分区按钮（与 Sidebar bg-[#2C2520] 一致）。
 * 选中态：amber 背景 `#C4873A`，未选中态：淡色 hover。
 */
function NavItem({ cfg, count, isSelected, onClick }: NavItemProps) {
  return (
    <button
      onClick={onClick}
      style={{
        width: '100%',
        textAlign: 'left',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '9px 14px',
        background: isSelected ? '#C4873A' : 'transparent',
        border: 'none',
        cursor: 'pointer',
        transition: 'background 0.1s',
        borderRadius: 0,
      }}
      onMouseEnter={e => {
        if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = '#3D342E'
      }}
      onMouseLeave={e => {
        if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'transparent'
      }}
    >
      <span style={{ color: isSelected ? '#fff' : '#9E8E80', flexShrink: 0 }}>
        {cfg.icon}
      </span>
      <span style={{
        fontSize: 13,
        fontWeight: isSelected ? 600 : 400,
        color: isSelected ? '#fff' : '#9E8E80',
        flex: 1,
      }}>
        {cfg.label}
      </span>
      {count > 0 && (
        <span style={{
          fontSize: 11,
          padding: '1px 7px',
          borderRadius: 10,
          background: isSelected ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.08)',
          color: isSelected ? '#fff' : '#9E8E80',
          fontVariantNumeric: 'tabular-nums',
        }}>
          {count}
        </span>
      )}
    </button>
  )
}

// ── 主页面 ────────────────────────────────────────────────────

/**
 * 项目生成纪要详情页。
 * 并行拉取所有生成数据后，渲染左侧分区导航和右侧富内容区。
 */
export default function BookshelfDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()

  const [data, setData] = useState<DetailData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedSection, setSelectedSection] = useState('overview')
  const [showWizard, setShowWizard] = useState(false)
  const [wizardRecoverRunId, setWizardRecoverRunId] = useState<string | null>(null)
  const [resumeBarHidden, setResumeBarHidden] = useState(false)
  const [resumeCancelLoading, setResumeCancelLoading] = useState(false)
  const { snapshot: bootstrapResumeSnapshot, refresh: refreshBootstrapResume } = useBootstrapResumeBanner(
    projectId ?? null,
  )

  const loadRecapData = useCallback(async (opts?: { silent?: boolean }) => {
    if (!projectId) return
    if (!opts?.silent) {
      setLoading(true)
      setError('')
    }
    try {
      const [
        projectRes, insightsRes, charsRes, relsRes,
        factionsRes, psRes, skillsRes, itemsRes,
        slRes, settingsRes, outlineRes,
      ] = await Promise.all([
        projectsApi.get(projectId),
        projectsApi.getInsights(projectId).catch(() => ({ data: { consistency_issues: [], opening_contract: {}, positioning: {} } })),
        charactersApi.list(projectId).catch(() => ({ data: [] })),
        charactersApi.listRelationships(projectId).catch(() => ({ data: [] })),
        factionsApi.list(projectId).catch(() => ({ data: [] })),
        powerSystemsApi.list(projectId).catch(() => ({ data: [] })),
        skillsApi.list(projectId).catch(() => ({ data: [] })),
        itemsApi.list(projectId).catch(() => ({ data: [] })),
        storylinesApi.list(projectId).catch(() => ({ data: [] })),
        settingsApi.list(projectId).catch(() => ({ data: [] })),
        outlineApi.getTree(projectId).catch(() => ({ data: [] })),
      ])
      const allNodes: OutlineNode[] = Array.isArray(outlineRes.data) ? outlineRes.data : []
      const volumes = allNodes.filter(n => n.node_type === 'volume')
      const project = projectRes.data
      const insightsPayload = insightsRes.data ?? {
        consistency_issues: [],
        opening_contract: {},
        positioning: {},
      }
      setData({
        project,
        insights: {
          ...insightsPayload,
          opening_contract: resolveOpeningContract(insightsPayload, project.extra),
          consistency_issues: insightsPayload.consistency_issues
            ?? project.extra?.consistency_issues
            ?? [],
          positioning: insightsPayload.positioning
            ?? project.extra?.positioning
            ?? {},
        },
        characters: Array.isArray(charsRes.data) ? charsRes.data : [],
        relations: Array.isArray(relsRes.data) ? relsRes.data : [],
        factions: Array.isArray(factionsRes.data) ? factionsRes.data : [],
        powerSystems: Array.isArray(psRes.data) ? psRes.data : [],
        skills: Array.isArray(skillsRes.data) ? skillsRes.data : [],
        items: Array.isArray(itemsRes.data) ? itemsRes.data : [],
        storylines: Array.isArray(slRes.data) ? slRes.data : [],
        settings: Array.isArray(settingsRes.data) ? settingsRes.data : [],
        volumes,
      })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载失败，请检查网络后重试'
      setError(msg)
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void loadRecapData()
  }, [loadRecapData])

  const handleCancelBootstrapRun = async () => {
    const rid = bootstrapResumeSnapshot?.runId?.trim()
    if (!rid) return
    setResumeCancelLoading(true)
    try {
      await bootstrapRunsApi.cancel(rid)
      clearActiveBootstrapRun()
      toast.success('已终止生成')
      await refreshBootstrapResume()
    } catch {
      toast.error('终止失败，请重试')
    } finally {
      setResumeCancelLoading(false)
    }
  }

  const handleWizardClose = () => {
    setShowWizard(false)
    setWizardRecoverRunId(null)
    void refreshBootstrapResume()
    if (data) void loadRecapData({ silent: true })
  }

  const openContinueBootstrap = () => {
    if (!bootstrapResumeSnapshot?.runId) return
    setResumeBarHidden(false)
    setWizardRecoverRunId(bootstrapResumeSnapshot.runId)
    setShowWizard(true)
  }

  // ── 加载态 ──────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{
        minHeight: '100vh', background: '#FAF8F4',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexDirection: 'column', gap: 12,
      }}>
        <Loader2 size={32} style={{ color: '#C4873A', animation: 'spin 1s linear infinite' }} />
        <p style={{ fontSize: 14, color: '#9ca3af' }}>加载结构化纪要…</p>
        <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>
      </div>
    )
  }

  // ── 错误态 ──────────────────────────────────────────────────
  if (error || !data) {
    return (
      <div style={{
        minHeight: '100vh', background: '#FAF8F4',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexDirection: 'column', gap: 12,
      }}>
        <AlertCircle size={32} style={{ color: '#ef4444' }} />
        <p style={{ fontSize: 14, color: '#6b7280' }}>{error || '项目不存在'}</p>
        <button
          onClick={() => navigate('/bookshelf')}
          style={{
            marginTop: 8, padding: '8px 20px', borderRadius: 8,
            background: '#fff', border: '1px solid #e5e7eb',
            color: '#374151', fontSize: 13, cursor: 'pointer',
          }}
        >
          返回书架
        </button>
      </div>
    )
  }

  const activeSec = SECTIONS.find(s => s.id === selectedSection) ?? SECTIONS[0]

  return (
    <div style={{
      minHeight: '100vh', height: '100vh',
      background: '#FAF8F4', display: 'flex', flexDirection: 'column',
      overflow: 'hidden', fontFamily: 'inherit',
    }}>
      {showWizard && (
        <GenerateWizard
          onClose={handleWizardClose}
          recoverRunId={wizardRecoverRunId}
          onRecoverConsumed={() => setWizardRecoverRunId(null)}
        />
      )}

      <RecapPageHeader
        title={data.project.title || ''}
        genre={data.project.genre}
        activeSectionLabel={activeSec.label}
        bootstrapResume={bootstrapResumeSnapshot}
        onContinueBootstrap={openContinueBootstrap}
        onEnterWorkbench={() => navigate(`/project/${projectId}/outline`)}
        onBackToDetail={() => navigate(projectId ? `/bookshelf/${projectId}` : '/bookshelf')}
        onBackToShelf={() => navigate('/bookshelf')}
      />

      <div style={{ flexShrink: 0, padding: '12px 20px 0', background: '#FAF8F4' }}>
        <ActiveBootstrapResumeBar
          snapshot={bootstrapResumeSnapshot}
          hidden={resumeBarHidden}
          onContinue={() => {
            if (!bootstrapResumeSnapshot?.runId) return
            setWizardRecoverRunId(bootstrapResumeSnapshot.runId)
            setShowWizard(true)
            setResumeBarHidden(false)
          }}
          onHide={() => setResumeBarHidden(true)}
          onCancelRun={handleCancelBootstrapRun}
          cancelLoading={resumeCancelLoading}
        />
      </div>

      {/* ── 主体：左导航 + 右内容 ───────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* 左侧深棕导航（与 Sidebar bg-[#2C2520] 一致）*/}
        <nav style={{
          width: 200, flexShrink: 0,
          background: '#2C2520',
          overflowY: 'auto', paddingTop: 8,
          scrollbarWidth: 'thin', scrollbarColor: '#3D342E transparent',
        }}>
          {/* 分区导航标题 */}
          <div style={{
            padding: '4px 14px 10px',
            fontSize: 10, fontWeight: 700, color: '#6B5E56',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}>
            生成纪要
          </div>

          {SECTIONS.map(sec => (
            <NavItem
              key={sec.id}
              cfg={sec}
              count={sec.countFn(data)}
              isSelected={selectedSection === sec.id}
              onClick={() => setSelectedSection(sec.id)}
            />
          ))}

          {/* 统计汇总 */}
          <div style={{
            margin: '16px 10px 12px',
            padding: '10px 12px',
            background: 'rgba(0,0,0,0.2)', borderRadius: 8,
            border: '1px solid rgba(255,255,255,0.06)',
          }}>
            <div style={{ fontSize: 10, color: '#6B5E56', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              数据汇总
            </div>
            {(
              [
                ['人物', data.characters.length],
                ['势力', data.factions.length],
                ['技能', data.skills.length],
                ['道具', data.items.length],
                ['设定卡', data.settings.length],
                ['卷', data.volumes.length],
              ] as [string, number][]
            ).map(([label, count]) => (
              count > 0 && (
                <div key={String(label)} style={{
                  display: 'flex', justifyContent: 'space-between',
                  fontSize: 12, color: '#9E8E80', marginBottom: 4,
                }}>
                  <span>{label}</span>
                  <span style={{ color: '#C4A882', fontVariantNumeric: 'tabular-nums' }}>{count}</span>
                </div>
              )
            ))}
          </div>
        </nav>

        {/* 右侧内容区（暖米色背景）*/}
        <main style={{
          flex: 1, overflowY: 'auto',
          background: '#FAF8F4',
          scrollbarWidth: 'thin', scrollbarColor: '#e5e7eb transparent',
        }}>
          {/* 内容区标题栏（白色粘性条）*/}
          <div style={{
            position: 'sticky', top: 0, zIndex: 10,
            background: '#ffffff',
            borderBottom: '1px solid #e5e7eb',
            padding: '12px 24px',
            display: 'flex', alignItems: 'center', gap: 10,
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <span style={{ color: activeSec.color }}>{activeSec.icon}</span>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: '#111827', margin: 0 }}>
              {activeSec.label}
            </h2>
            {activeSec.countFn(data) > 0 && (
              <span style={{
                fontSize: 12, padding: '2px 8px', borderRadius: 10,
                background: '#fef3c7', color: '#b45309',
                border: '1px solid #fde68a',
              }}>
                {activeSec.countFn(data)} 条
              </span>
            )}
          </div>

          {/* 实际内容 */}
          <div style={{ padding: '20px 24px 40px' }}>
            <SectionContent sectionId={selectedSection} data={data} />
          </div>
        </main>
      </div>
    </div>
  )
}
