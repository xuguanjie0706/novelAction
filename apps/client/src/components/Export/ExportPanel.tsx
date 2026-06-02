/**
 * ExportPanel.tsx — 导出 & 投稿面板
 *
 * 功能：
 *   1. 平台选择 + 字数合规预检（毫秒响应，无 AI）
 *   2. AI 违禁词预审（按章节批量扫描，展示风险条目和修改建议）
 *   3. TXT 全文下载 / ZIP 投稿包下载
 *
 * 数据来源：全部从后端 /api/v1/projects/{pid}/export/* 获取，
 * 不依赖全局 store（导出是独立低频操作）。
 */
import { useState, useEffect, useCallback } from 'react'
import {
  X,
  Download,
  FileText,
  ListTree,
  Package,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  Info,
} from 'lucide-react'
import api from '../../api/client'
import toast from 'react-hot-toast'

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface PlatformRule {
  name: string
  min_words: number
  max_words: number
}

interface ChapterIssue {
  chapter_id: string
  title: string
  sort_order: number
  word_count: number
  status: 'ok' | 'too_short' | 'too_long' | 'empty'
  message: string
}

interface ExportPreview {
  total_chapters: number
  total_words: number
  platform: string
  platform_name: string
  compliant_chapters: number
  issues: ChapterIssue[]
  platforms: Record<string, PlatformRule>
}

interface ViolationIssue {
  category: string
  level: 'warn' | 'block'
  excerpt: string
  reason: string
  suggestion: string
}

interface ChapterScanResult {
  chapter_id: string
  chapter_title: string
  overall_risk: 'low' | 'medium' | 'high' | 'unknown'
  summary: string
  issues: ViolationIssue[]
}

interface ViolationScanOut {
  results: ChapterScanResult[]
  total_issues: number
  has_high_risk: boolean
}

// ── 辅助组件 ──────────────────────────────────────────────────────────────────

/** 风险等级徽章 */
function RiskBadge({ risk }: { risk: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    low:     { label: '低风险', cls: 'bg-green-100 text-green-700' },
    medium:  { label: '中风险', cls: 'bg-amber-100 text-amber-700' },
    high:    { label: '高风险', cls: 'bg-red-100 text-red-700' },
    unknown: { label: '未知',   cls: 'bg-gray-100 text-gray-500' },
  }
  const { label, cls } = map[risk] ?? map.unknown
  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${cls}`}>
      {label}
    </span>
  )
}

/** 单章违禁词扫描结果展开行 */
function ChapterScanRow({ result }: { result: ChapterScanResult }) {
  const [open, setOpen] = useState(result.overall_risk !== 'low')

  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-gray-50 transition-colors"
      >
        {open ? <ChevronDown size={13} className="text-gray-400 shrink-0" /> : <ChevronRight size={13} className="text-gray-400 shrink-0" />}
        <span className="flex-1 text-xs font-medium text-gray-700 truncate">{result.chapter_title}</span>
        <RiskBadge risk={result.overall_risk} />
        <span className="text-[10px] text-gray-400 shrink-0">{result.issues.length} 项</span>
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2 bg-gray-50 border-t border-gray-100">
          <p className="text-[11px] text-gray-500 pt-2">{result.summary}</p>
          {result.issues.length === 0 ? (
            <p className="text-[11px] text-green-600 flex items-center gap-1">
              <CheckCircle2 size={11} /> 未检测到明显违规内容
            </p>
          ) : (
            result.issues.map((issue, i) => (
              <div key={i} className={`rounded-md p-2.5 text-[11px] space-y-1 ${
                issue.level === 'block' ? 'bg-red-50 border border-red-100' : 'bg-amber-50 border border-amber-100'
              }`}>
                <div className="flex items-center gap-1.5 font-medium">
                  <AlertTriangle size={11} className={issue.level === 'block' ? 'text-red-500' : 'text-amber-500'} />
                  <span className={issue.level === 'block' ? 'text-red-700' : 'text-amber-700'}>{issue.category}</span>
                </div>
                <p className="text-gray-500 italic">「{issue.excerpt}」</p>
                <p className="text-gray-600">{issue.reason}</p>
                <p className="text-blue-700 font-medium">💡 {issue.suggestion}</p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

interface ExportPanelProps {
  /** 当前项目 ID */
  projectId: string
  /** 关闭面板的回调 */
  onClose: () => void
}

/**
 * ExportPanel — 导出 & 投稿面板。
 *
 * 挂载时自动拉取合规预检数据（GET /export/preview），
 * 违禁词扫描需用户主动触发（POST /export/scan-violations）。
 */
export default function ExportPanel({ projectId, onClose }: ExportPanelProps) {
  const [platform, setPlatform]           = useState('general')
  const [preview, setPreview]             = useState<ExportPreview | null>(null)
  const [loadingPreview, setLoadingPreview] = useState(false)

  const [scanning, setScanning]           = useState(false)
  const [scanResult, setScanResult]       = useState<ViolationScanOut | null>(null)

  const [downloading, setDownloading]     = useState<'txt' | 'zip' | 'outline' | null>(null)

  // ── 拉取合规预检 ──────────────────────────────────────────────────────────
  const fetchPreview = useCallback(async (p: string) => {
    setLoadingPreview(true)
    try {
      const res = await api.get<ExportPreview>(
        `/projects/${projectId}/export/preview`,
        { params: { platform: p } },
      )
      setPreview(res.data)
    } catch {
      toast.error('获取导出预览失败')
    } finally {
      setLoadingPreview(false)
    }
  }, [projectId])

  useEffect(() => { fetchPreview(platform) }, [platform, fetchPreview])

  // ── AI 违禁词预审 ─────────────────────────────────────────────────────────
  const runViolationScan = async () => {
    if (!preview || preview.total_chapters === 0) return
    setScanning(true)
    setScanResult(null)

    try {
      // 取所有有字数的章节 ID（从 preview.issues 反推出不在 issues 或 issues 里非 empty 的都要扫）
      // 后端会从 project_id 找章节，前端传 chapter_ids 列表；
      // 这里先拉章节列表再传（复用 preview 中已知 issues 筛选）
      const chaptersRes = await api.get<{ id: string; word_count: number }[]>(
        `/projects/${projectId}/chapters/`,
      )
      const toScan = chaptersRes.data
        .filter(c => (c.word_count ?? 0) > 0)
        .map(c => c.id)
        .slice(0, 20)  // 最多扫 20 章，避免超时

      if (toScan.length === 0) {
        toast.error('暂无有内容的章节可扫描')
        return
      }

      const res = await api.post<ViolationScanOut>(
        `/projects/${projectId}/export/scan-violations`,
        { chapter_ids: toScan, platform },
      )
      setScanResult(res.data)
    } catch {
      toast.error('违禁词扫描失败，请稍后重试')
    } finally {
      setScanning(false)
    }
  }

  // ── 下载 ──────────────────────────────────────────────────────────────────
  const download = async (type: 'txt' | 'package' | 'outline') => {
    setDownloading(type === 'package' ? 'zip' : type)
    try {
      const url = `/api/v1/projects/${projectId}/export/${type}`
      const token = localStorage.getItem('novelAction:auth-token')
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || '下载失败')
      }
      const blob = await res.blob()
      const disp = res.headers.get('Content-Disposition') || ''
      // 从 filename*=UTF-8''xxx 或 filename="xxx" 提取文件名
      let filename =
        type === 'txt' ? 'novel.txt'
        : type === 'outline' ? 'novel_大纲.txt'
        : 'novel_投稿包.zip'
      const m = disp.match(/filename\*=UTF-8''([^;]+)/) ?? disp.match(/filename="([^"]+)"/)
      if (m) filename = decodeURIComponent(m[1])

      const objUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objUrl
      a.download = filename
      a.click()
      URL.revokeObjectURL(objUrl)
    } catch (e: any) {
      toast.error(e?.message ?? '下载失败')
    } finally {
      setDownloading(null)
    }
  }

  // ── 渲染 ──────────────────────────────────────────────────────────────────
  const platforms = preview?.platforms ?? {}

  const issueCount = preview?.issues.filter(i => i.status !== 'empty').length ?? 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div className="flex items-center gap-2">
            <Package size={18} className="text-amber-500" />
            <h2 className="text-base font-semibold text-gray-800">导出 & 投稿</h2>
          </div>
          <button type="button" onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* ── 平台选择 ── */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">目标平台</h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(platforms).length > 0 ? (
                Object.entries(platforms).map(([key, rule]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setPlatform(key)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      platform === key
                        ? 'bg-amber-500 border-amber-500 text-white'
                        : 'bg-white border-gray-200 text-gray-600 hover:border-amber-300'
                    }`}
                  >
                    {rule.name}
                    <span className="ml-1 opacity-70">
                      {rule.min_words > 0 ? `${rule.min_words / 1000}k-${rule.max_words / 1000}k字` : '不限'}
                    </span>
                  </button>
                ))
              ) : (
                // 骨架占位
                ['起点中文网', '晋江文学城', '番茄小说', '通用'].map(n => (
                  <div key={n} className="h-8 w-24 bg-gray-100 rounded-lg animate-pulse" />
                ))
              )}
            </div>
          </section>

          {/* ── 合规预检 ── */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">字数合规预检</h3>
            {loadingPreview ? (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader2 size={14} className="animate-spin" /> 检查中...
              </div>
            ) : preview ? (
              <div className="space-y-3">
                {/* 总览卡 */}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: '章节总数', value: preview.total_chapters },
                    { label: '总字数',   value: `${(preview.total_words / 10000).toFixed(1)} 万` },
                    { label: '合规章节', value: `${preview.compliant_chapters} / ${preview.total_chapters}` },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-gray-50 rounded-xl p-3 text-center">
                      <div className="text-lg font-bold text-gray-800">{value}</div>
                      <div className="text-[10px] text-gray-400 mt-0.5">{label}</div>
                    </div>
                  ))}
                </div>

                {/* 问题章节 */}
                {issueCount > 0 ? (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-[11px] text-amber-600 font-medium mb-1.5">
                      <AlertTriangle size={11} />
                      {issueCount} 个章节不符合 {preview.platform_name} 字数要求
                    </div>
                    {preview.issues.filter(i => i.status !== 'empty').map(issue => (
                      <div key={issue.chapter_id}
                        className="flex items-center gap-2 text-[11px] px-2.5 py-1.5 bg-amber-50 rounded-lg border border-amber-100">
                        <span className="text-amber-500 font-medium shrink-0">第{issue.sort_order}章</span>
                        <span className="flex-1 text-gray-600 truncate">{issue.title}</span>
                        <span className="text-amber-600 shrink-0">{issue.message}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 text-[11px] text-green-600">
                    <CheckCircle2 size={12} />
                    所有章节符合 {preview.platform_name} 字数要求
                  </div>
                )}

                {/* 空章节提示 */}
                {preview.issues.filter(i => i.status === 'empty').length > 0 && (
                  <div className="flex items-center gap-1.5 text-[11px] text-gray-400">
                    <Info size={11} />
                    {preview.issues.filter(i => i.status === 'empty').length} 个空章节将在导出时自动跳过
                  </div>
                )}
              </div>
            ) : null}
          </section>

          {/* ── AI 违禁词预审 ── */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">AI 违禁词预审</h3>
              <button
                type="button"
                onClick={runViolationScan}
                disabled={scanning || !preview || preview.total_chapters === 0}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-purple-500 hover:bg-purple-600 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {scanning
                  ? <><Loader2 size={12} className="animate-spin" /> 扫描中...</>
                  : <><ShieldAlert size={12} /> 开始扫描</>}
              </button>
            </div>

            {!scanResult && !scanning && (
              <p className="text-[11px] text-gray-400 leading-relaxed">
                AI 扫描章节内容，识别可能触发审核的段落并给出修改建议。
                扫描结果仅供参考，最终投稿前请作者自行判断。
              </p>
            )}

            {scanResult && (
              <div className="space-y-2">
                {/* 扫描总结 */}
                <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium ${
                  scanResult.has_high_risk
                    ? 'bg-red-50 text-red-700 border border-red-100'
                    : scanResult.total_issues > 0
                      ? 'bg-amber-50 text-amber-700 border border-amber-100'
                      : 'bg-green-50 text-green-700 border border-green-100'
                }`}>
                  {scanResult.has_high_risk
                    ? <ShieldAlert size={13} />
                    : <ShieldCheck size={13} />}
                  共发现 {scanResult.total_issues} 处风险点，涉及 {scanResult.results.filter(r => r.issues.length > 0).length} 章
                </div>

                {/* 章节展开列表 */}
                <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
                  {scanResult.results.map(r => (
                    <ChapterScanRow key={r.chapter_id} result={r} />
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>

        {/* 底部下载按钮 */}
        <div className="flex items-center gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50 shrink-0">
          <button
            type="button"
            onClick={() => download('outline')}
            disabled={downloading !== null || !preview}
            title="导出卷 → 篇章 → 章节计划的全书大纲"
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-white border border-gray-200 hover:border-amber-300 text-gray-700 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {downloading === 'outline'
              ? <Loader2 size={14} className="animate-spin" />
              : <ListTree size={14} />}
            下载大纲
          </button>
          <button
            type="button"
            onClick={() => download('txt')}
            disabled={downloading !== null || !preview || preview.compliant_chapters === 0}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {downloading === 'txt'
              ? <Loader2 size={14} className="animate-spin" />
              : <FileText size={14} />}
            下载 TXT 全文
          </button>
          <button
            type="button"
            onClick={() => download('package')}
            disabled={downloading !== null || !preview || preview.compliant_chapters === 0}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gray-700 hover:bg-gray-800 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {downloading === 'zip'
              ? <Loader2 size={14} className="animate-spin" />
              : <Package size={14} />}
            下载 ZIP 投稿包
          </button>
        </div>
      </div>
    </div>
  )
}
