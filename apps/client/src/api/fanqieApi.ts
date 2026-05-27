/**
 * @file api/fanqieApi.ts — 番茄小说代理 API
 *
 * 通过后端 /api/v1/fanqie/* 代理调用番茄小说作者 API，
 * 避免浏览器 CORS 限制。凭据存储在后端 fanqie_creds.json。
 */
import { api } from './base'

// ──────────────────────────────────────────────────────────
// 类型定义
// ──────────────────────────────────────────────────────────

export interface FanqieConfig {
  cookies: string
  csrf_token?: string
  ms_token?: string
  a_bogus?: string
  author_id?: string
}

export interface FanqieConfigSummary {
  configured: boolean
  session_preview?: string
  author_id?: string
  has_csrf_token?: boolean
  has_ms_token?: boolean
  has_a_bogus?: boolean
}

export interface FanqiePublishRequest {
  mode: 'create' | 'existing'
  book_id?: string
  /** 番茄书名，留空则用项目标题（后端截断至 15 字） */
  book_name?: string
  category?: string
  gender?: number
  roles?: string[]
  thumb_uri?: string
  volume_id?: string
  volume_name?: string
  delay_seconds?: number
  chapter_ids?: string[]
  /** DevTools 复制的 book/create cURL，刷新 a_bogus */
  fresh_create_curl?: string
  /** 创建新书时自动上传项目封面 */
  upload_cover?: boolean
}

export interface FanqiePublishChapterResult {
  chapter_id: string
  title: string
  item_id?: string
  status: string
  message?: string
}

export interface FanqiePublishResponse {
  book_id: string
  created: boolean
  cover_uploaded?: boolean
  thumb_uri?: string | null
  uploaded: FanqiePublishChapterResult[]
  failed: FanqiePublishChapterResult[]
  total_chapters: number
}

export interface FanqieBook {
  book_id: string
  book_name: string
  cover?: string | null
  abstract?: string
  word_count?: number
  chapter_count?: number
  /** creation_status：0=已完结，1=连载中 */
  status?: number
  create_time?: number
  update_time?: number
  last_chapter_title?: string
}

export interface FanqieChapter {
  item_id: string
  title: string
  word_count?: number
  create_time?: number
  update_time?: number
  is_published?: boolean
  status?: number
  volume_id?: string
  index?: number
}

export interface FanqieBooksResponse {
  books: FanqieBook[]
  total?: number
}

export interface FanqieChaptersResponse {
  chapters: FanqieChapter[]
  total?: number
  draft_count?: number
  published_count?: number
}

export interface FanqieUserInfo {
  author_name?: string
  avatar_url?: string
  fan_count?: number
  word_count?: number
  author_id?: string
}

// ──────────────────────────────────────────────────────────
// API 函数
// ──────────────────────────────────────────────────────────

/**
 * 保存番茄凭据到后端。
 * Cookie 字符串直接从 DevTools「Copy as cURL」的 -b '...' 里粘贴。
 */
export async function saveFanqieConfig(config: FanqieConfig): Promise<void> {
  await api.post('/fanqie/config', config)
}

/** 读取当前凭据摘要（敏感字段已脱敏）。 */
export async function getFanqieConfigSummary(): Promise<FanqieConfigSummary> {
  const res = await api.get<FanqieConfigSummary>('/fanqie/config')
  return res.data
}

/** 获取番茄作者信息（头像、粉丝数等）。 */
export async function getFanqieUser(): Promise<FanqieUserInfo> {
  const res = await api.get<FanqieUserInfo>('/fanqie/user')
  return res.data
}

/** 获取当前账号的书籍列表（后端已归一化）。 */
export async function getFanqieBooks(
  pageIndex = 0,
  pageCount = 20,
): Promise<FanqieBooksResponse> {
  const res = await api.get<FanqieBooksResponse>('/fanqie/books', {
    params: { page_index: pageIndex, page_count: pageCount },
  })
  return res.data
}

/**
 * 获取某书下的章节/草稿列表。
 *
 * @param bookId  番茄书籍 ID
 * @param status  "0" 全部 / "1" 已发布 / "2" 草稿
 */
export async function getFanqieChapters(
  bookId: string,
  status = '0',
  pageIndex = 0,
  pageCount = 50,
): Promise<FanqieChaptersResponse> {
  const res = await api.get<FanqieChaptersResponse>(`/fanqie/books/${bookId}/chapters`, {
    params: { status, page_index: pageIndex, page_count: pageCount },
  })
  return res.data
}

/**
 * 将 novelAction 项目发布到番茄（创建新书或上传到已有书 + 章节草稿）。
 */
export async function publishProjectToFanqie(
  projectId: string,
  body: FanqiePublishRequest,
): Promise<FanqiePublishResponse> {
  const res = await api.post<FanqiePublishResponse>(`/fanqie/projects/${projectId}/publish`, body)
  return res.data
}

/**
 * 上传封面到番茄 upload_pic_v1，返回 thumb_uri（如 novel-pic-r/xxx）。
 */
export async function uploadFanqieCover(
  file: File,
  options?: { bookId?: string; freshCurl?: string },
): Promise<{ thumb_uri: string }> {
  const fd = new FormData()
  fd.append('file', file)
  const params = new URLSearchParams()
  if (options?.bookId?.trim()) params.set('book_id', options.bookId.trim())
  if (options?.freshCurl?.trim()) params.set('fresh_curl', options.freshCurl.trim())
  const qs = params.toString()
  const url = `/api/v1/fanqie/upload-cover${qs ? `?${qs}` : ''}`

  const token = (() => {
    try {
      return localStorage.getItem('novelAction:auth-token')
    } catch {
      return null
    }
  })()

  const res = await fetch(url, {
    method: 'POST',
    body: fd,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(err.detail ?? `上传失败 HTTP ${res.status}`)
  }
  return res.json() as Promise<{ thumb_uri: string }>
}
