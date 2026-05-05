import axios from 'axios'

/** 列表/轻量接口 */
export const DEFAULT_HTTP_TIMEOUT_MS = 60_000

/**
 * 与后端 `LLM_HTTP_READ_TIMEOUT`（默认 900s）对齐；连贯性评测/改正文等请求勿用 60s 默认超时。
 */
export const LONG_RUNNING_HTTP_TIMEOUT_MS = 900_000

export const http = axios.create({
  baseURL: '',
  timeout: DEFAULT_HTTP_TIMEOUT_MS,
})
