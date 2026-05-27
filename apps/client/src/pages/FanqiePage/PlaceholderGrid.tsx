/**
 * PlaceholderGrid — 未连接番茄时的弱态书架占位
 *
 * 点击任意占位卡唤起连接弹窗，视觉上与真实书架网格一致但降低透明度。
 */
import React from 'react'
import { Flame, Link2 } from 'lucide-react'
import { PLACEHOLDER_TITLES } from './fanqieUtils'

interface Props {
  onConnect: () => void
}

function GhostCard({ title, highlight }: { title: string; highlight?: boolean }) {
  return (
    <button
      type="button"
      className={`group flex flex-col overflow-hidden rounded-xl border text-left transition-all ${
        highlight
          ? 'border-dashed border-red-200/80 bg-white/80 hover:border-red-300 hover:shadow-md'
          : 'border-gray-100/60 bg-white/40 hover:bg-white/60'
      }`}
    >
      <div
        className={`relative flex h-48 w-full items-center justify-center ${
          highlight
            ? 'bg-gradient-to-br from-red-50 to-orange-50'
            : 'bg-gradient-to-br from-gray-100 to-gray-200/80'
        }`}
      >
        {highlight ? (
          <div className="flex flex-col items-center gap-2 px-4 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
              <Link2 size={22} className="text-red-400" />
            </div>
            <span className="text-sm font-semibold text-red-500/90">连接番茄账号</span>
            <span className="text-[11px] text-gray-400">粘贴 cURL 即可同步作品</span>
          </div>
        ) : (
          <>
            <Flame size={28} className="text-gray-300/70" />
            <div className="absolute inset-0 bg-white/20" />
          </>
        )}
      </div>
      <div className="px-4 py-3">
        <div
          className={`h-4 rounded ${
            highlight ? 'w-24 bg-red-100/80' : 'w-full max-w-[8rem] bg-gray-200/60'
          }`}
        />
        {!highlight && (
          <p className="mt-2 text-[11px] text-gray-400/80">{title}</p>
        )}
      </div>
    </button>
  )
}

export default function PlaceholderGrid({ onConnect }: Props) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onConnect}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onConnect()
        }
      }}
      className="cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-4 rounded-xl"
      aria-label="点击连接番茄作家后台"
    >
      <div className="mb-4 flex items-center justify-center gap-2 text-sm text-gray-400/90">
        <Flame size={14} className="text-red-300" />
        <span>尚未连接番茄 · 点击任意位置开始配置</span>
      </div>

      <div className="grid gap-6 opacity-[0.72] transition-opacity hover:opacity-90 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        <GhostCard title="" highlight />
        {PLACEHOLDER_TITLES.map(title => (
          <GhostCard key={title} title={title} />
        ))}
      </div>
    </div>
  )
}
