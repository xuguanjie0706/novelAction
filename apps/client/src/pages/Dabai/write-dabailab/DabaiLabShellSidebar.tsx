import { Link, useParams, useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import {
  ArrowLeft, Brain, FileText, Globe, Layers, Milestone, Package, ShieldCheck, Users,
} from 'lucide-react'
import { parseWorkspaceTab, type WorkspaceTab } from './workspaceTab'

const NAV: { tab: WorkspaceTab; icon: typeof FileText; label: string }[] = [
  { tab: 'write', icon: FileText, label: '写作' },
  { tab: 'volumes', icon: Layers, label: '卷纲' },
  { tab: 'characters', icon: Users, label: '人物' },
  { tab: 'world', icon: Globe, label: '设定' },
  { tab: 'quality', icon: ShieldCheck, label: '卷纲质检' },
  { tab: 'memory', icon: Brain, label: '记忆' },
  { tab: 'clues', icon: Milestone, label: '线索' },
  { tab: 'ledger', icon: Package, label: '台账' },
]

export default function DabaiLabShellSidebar() {
  const { projectId } = useParams<{ projectId: string }>()
  const [searchParams] = useSearchParams()
  const active = parseWorkspaceTab(searchParams.get('tab'))
  const base = `/dabai/${projectId}/write-dabailab`

  return (
    <aside className="flex w-14 shrink-0 flex-col items-center gap-1 bg-[#2C2520] py-4">
      <Link
        to="/dabai"
        title="返回书架"
        className="mb-2 flex h-12 w-10 flex-col items-center justify-center gap-0.5 rounded-lg text-[#9E8E80] transition-colors hover:bg-[#3D342E] hover:text-white"
      >
        <ArrowLeft size={18} />
        <span className="text-[10px]">书架</span>
      </Link>
      {NAV.map(({ tab, icon: Icon, label }) => {
        const to = tab === 'write' ? base : `${base}?tab=${tab}`
        const isActive = active === tab
        return (
          <Link
            key={tab}
            to={to}
            title={label}
            className={clsx(
              'flex h-12 w-10 flex-col items-center justify-center gap-0.5 rounded-lg text-xs transition-colors',
              isActive ? 'bg-[#C4873A] text-white' : 'text-[#9E8E80] hover:bg-[#3D342E] hover:text-white',
            )}
          >
            <Icon size={18} />
            <span>{label}</span>
          </Link>
        )
      })}
    </aside>
  )
}
