import React from 'react'
import { NavLink } from 'react-router-dom'
import { BarChart2, BookOpen, Users, Map, FileText, Brain, Globe, Bookmark, BookMarked } from 'lucide-react'
import clsx from 'clsx'

interface Props { projectId: string }

const NAV = [
  { to: 'outline',       icon: BookOpen, label: '大纲' },
  { to: 'write',         icon: FileText, label: '写作' },
  { to: 'characters',    icon: Users,    label: '人物' },
  { to: 'worldbuilding', icon: Globe,    label: '世界' },
  { to: 'settings',      icon: Map,      label: '设定' },
  { to: 'memory',        icon: Brain,     label: '记忆库' },
  { to: 'clues',         icon: Bookmark,    label: '线索' },
  { to: 'promises',      icon: BookMarked,  label: '承诺' },
  { to: 'rhythmmap',     icon: BarChart2,   label: '节奏' },
]

export default function Sidebar({ projectId }: Props) {
  return (
    <aside className="w-14 flex flex-col items-center py-4 bg-[#2C2520] gap-1">
      {NAV.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={`/project/${projectId}/${to}`}
          title={label}
          className={({ isActive }) => clsx(
            'flex flex-col items-center gap-0.5 w-10 h-12 rounded-lg justify-center text-xs transition-colors',
            isActive
              ? 'bg-[#C4873A] text-white'
              : 'text-[#9E8E80] hover:text-white hover:bg-[#3D342E]'
          )}
        >
          <Icon size={18} />
          <span>{label}</span>
        </NavLink>
      ))}
    </aside>
  )
}
