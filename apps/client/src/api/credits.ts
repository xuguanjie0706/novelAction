/**
 * 积分 API 客户端。
 *
 * 职责：封装对 `/api/v1/credits/me` 的请求，供 useCreditBalance hook 调用。
 * 数据来源：后端 routers/credits.py（Bearer token 鉴权）。
 */

import { authFetch } from './authFetch'

/** 用户积分账户摘要 */
export interface CreditBalance {
  user_id: string
  /** 当前可用余额（积分） */
  balance: number
  /** 历史累计消耗 */
  total_consumed: number
  /** 历史累计充值 / 赠送 */
  total_topped_up: number
  updated_at: string | null
}

/** 积分流水条目 */
export interface CreditTransaction {
  id: string
  user_id: string
  /** 变动量：正=充值，负=扣费 */
  delta: number
  balance_after: number
  /** 来源类型：registration_bonus / llm_call / admin_topup / admin_adjust / redeem_code */
  ref_type: string
  ref_id: string | null
  model: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  task: string | null
  note: string | null
  created_at: string
}

/**
 * 查询当前用户积分余额。
 *
 * @returns CreditBalance 对象；请求失败时抛出 Error。
 */
export async function fetchMyCredits(): Promise<CreditBalance> {
  const res = await authFetch('/api/v1/credits/me')
  if (!res.ok) throw new Error(`积分查询失败 (${res.status})`)
  return res.json()
}

/**
 * 查询当前用户积分流水。
 *
 * @param limit  每页条数（默认 50）
 * @param offset 分页偏移（默认 0）
 * @returns 流水列表；请求失败时抛出 Error。
 */
export async function fetchMyTransactions(
  limit = 50,
  offset = 0,
): Promise<CreditTransaction[]> {
  const res = await authFetch(
    `/api/v1/credits/me/transactions?limit=${limit}&offset=${offset}`,
  )
  if (!res.ok) throw new Error(`流水查询失败 (${res.status})`)
  return res.json()
}

/** 兑换码核销结果 */
export interface RedeemResult {
  code: string
  /** 本次兑换获得的积分 */
  credits: number
  /** 兑换后最新余额 */
  balance_after: number
  note: string | null
}

/**
 * 核销兑换码，将积分充入当前账户。
 *
 * @param code 兑换码字符串（大小写不敏感）
 * @returns 兑换结果；请求失败时抛出带服务器 detail 的 Error。
 */
export async function redeemCode(code: string): Promise<RedeemResult> {
  const res = await authFetch('/api/v1/credits/redeem', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail ?? `兑换失败 (${res.status})`)
  }
  return res.json()
}
