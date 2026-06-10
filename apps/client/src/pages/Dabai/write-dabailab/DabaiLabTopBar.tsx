import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import LlmAgentMenu from '../../../components/Layout/LlmAgentMenu'

interface Props {
  title: string
}

export default function DabaiLabTopBar({ title }: Props) {
  return (
    <header className="flex h-11 shrink-0 items-center gap-3 border-b border-gray-200/80 bg-[#FAF8F4] px-4">
      <Link
        to="/dabai"
        className="flex items-center gap-1 text-xs text-gray-500 transition-colors hover:text-gray-900 lg:hidden"
      >
        <ArrowLeft size={14} />
        书架
      </Link>
      <h1 className="min-w-0 flex-1 truncate text-sm font-semibold text-gray-900">{title}</h1>
      <LlmAgentMenu />
    </header>
  )
}
