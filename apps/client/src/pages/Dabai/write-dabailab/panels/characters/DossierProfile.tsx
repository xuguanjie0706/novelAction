/**
 * 档案区块构建器 —— 把人物的「静态底色」拆成若干独立区块（人设 / 故事功能 /
 * 角色内核 / 语言风格 / 代表台词 / 其他设定），供瀑布流铺平展开。
 */
import clsx from 'clsx'
import { Flame, HeartCrack, User, Target, Quote, Notebook } from 'lucide-react'
import {
  GROUP_ACCENT, classifyRole, field, FieldRow,
  type DabaiChar, type DossierSection,
} from './charMeta'

const HANDLED = new Set([
  'name', 'role', 'tier', 'start_realm', 'persona', 'function',
  'desire', 'wound', 'speech_kit', 'speech_style', 'golden_finger',
])

function pickQuote(raw: unknown): string {
  if (typeof raw === 'string') return raw.split(/[。！？.!?]/)[0]
  if (raw && typeof raw === 'object') {
    const s = (raw as Record<string, unknown>).sample_dialogues
    if (Array.isArray(s) && s.length) return String(s[0])
  }
  return ''
}

function speechMeta(raw: unknown): { label: string; value: string }[] {
  if (!raw || typeof raw !== 'object') return []
  const k = raw as Record<string, unknown>
  const arr = (v: unknown) => (Array.isArray(v) ? v.map(String).join('、') : '')
  return [
    { label: '口头禅', value: arr(k.signature_words) },
    { label: '禁忌词', value: arr(k.taboo_words) },
    { label: '句长', value: field(k as DabaiChar, 'sentence_length_pref') },
    { label: '独白', value: field(k as DabaiChar, 'inner_monologue_style') },
  ].filter(x => x.value)
}

const para = (t: string) => <p className="text-sm leading-relaxed text-gray-700">{t}</p>

export function profileSections(c: DabaiChar): DossierSection[] {
  const out: DossierSection[] = []
  const group = classifyRole(field(c, 'role'))
  const speech = c.speech_kit ?? c.speech_style
  const desire = field(c, 'desire')
  const wound = field(c, 'wound')
  const quote = pickQuote(speech)
  const meta = speechMeta(speech)
  const extras = Object.keys(c).filter(k => !HANDLED.has(k) && field(c, k))

  if (field(c, 'persona')) out.push({ key: 'persona', title: '人设 · 性格', icon: <User size={13} />, body: para(field(c, 'persona')) })
  if (field(c, 'function')) out.push({ key: 'function', title: '故事功能', icon: <Target size={13} />, body: para(field(c, 'function')) })

  if (desire || wound) {
    out.push({
      key: 'core', title: '角色内核',
      body: (
        <div className="space-y-2">
          {desire ? (
            <div className="flex gap-2 text-sm leading-relaxed text-gray-700">
              <Flame size={15} className="mt-0.5 shrink-0 text-rose-400" />
              <span><span className="text-gray-400">欲望 · </span>{desire}</span>
            </div>
          ) : null}
          {wound ? (
            <div className="flex gap-2 text-sm leading-relaxed text-gray-700">
              <HeartCrack size={15} className="mt-0.5 shrink-0 text-slate-400" />
              <span><span className="text-gray-400">伤痕 · </span>{wound}</span>
            </div>
          ) : null}
        </div>
      ),
    })
  }

  if (meta.length > 0) {
    out.push({
      key: 'speech', title: '语言风格', icon: <Quote size={13} />,
      body: <dl className="space-y-1.5">{meta.map(m => <FieldRow key={m.label} label={m.label} value={m.value} />)}</dl>,
    })
  }

  if (quote) {
    out.push({
      key: 'quote', title: '代表台词',
      body: (
        <blockquote className={clsx('rounded-none border-l-2 py-0.5 pl-3 font-serif text-[15px] leading-relaxed text-gray-800', GROUP_ACCENT[group].quote)}>
          「{quote}」
        </blockquote>
      ),
    })
  }

  if (extras.length > 0) {
    out.push({
      key: 'extras', title: '其他设定', icon: <Notebook size={13} />,
      body: <dl className="space-y-1.5">{extras.map(k => <FieldRow key={k} label={k} value={field(c, k)} />)}</dl>,
    })
  }
  return out
}
