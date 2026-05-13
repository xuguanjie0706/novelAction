/**
 * UserCreditsPage — 管理员积分管理页。
 *
 * 功能：
 * 1. 分页列出所有用户的积分账户（用户名 / 邮箱 / 余额 / 累计消耗 / 累计充值）。
 * 2. 点击某行展开该用户最近 50 条流水（Drawer）。
 * 3. 弹窗充值（Topup）或调账（Adjust）。
 *
 * 数据来源：`/api/v1/admin/credits`（需 admin token）。
 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Descriptions,
  Drawer,
  Form,
  InputNumber,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  Input,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined, EditOutlined, HistoryOutlined } from '@ant-design/icons'
import { http } from '../api/http'

const { Text } = Typography

// ── 类型定义 ──────────────────────────────────────────────────

interface UserCreditRow {
  user_id: string
  email: string | null
  username: string | null
  balance: number
  total_consumed: number
  total_topped_up: number
  created_at: string | null
  updated_at: string | null
}

interface CreditTransaction {
  id: string
  delta: number
  balance_after: number
  ref_type: string
  ref_id: string | null
  model: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  task: string | null
  note: string | null
  created_at: string
}

type ActionMode = 'topup' | 'adjust'

const REF_TYPE_LABEL: Record<string, string> = {
  registration_bonus: '注册赠送',
  llm_call: 'AI 调用',
  admin_topup: '管理员充值',
  admin_adjust: '管理员调整',
  redeem_code: '兑换码',
}

// ── 主组件 ────────────────────────────────────────────────────

export default function UserCreditsPage() {
  const { message } = App.useApp()

  // 列表状态
  const [rows, setRows] = useState<UserCreditRow[]>([])
  const [loading, setLoading] = useState(false)

  // 流水 Drawer
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserCreditRow | null>(null)
  const [transactions, setTransactions] = useState<CreditTransaction[]>([])
  const [txnLoading, setTxnLoading] = useState(false)

  // 操作弹窗
  const [modalOpen, setModalOpen] = useState(false)
  const [actionMode, setActionMode] = useState<ActionMode>('topup')
  const [actionTarget, setActionTarget] = useState<UserCreditRow | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [form] = Form.useForm<{ amount?: number; delta?: number; note?: string }>()

  // ── 数据加载 ────────────────────────────────────────────────
  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const res = await http.get<UserCreditRow[]>('/api/v1/admin/credits?limit=200')
      setRows(res.data)
    } catch {
      message.error('加载积分列表失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => { loadList() }, [loadList])

  // ── 流水加载 ────────────────────────────────────────────────
  const openDrawer = useCallback(async (row: UserCreditRow) => {
    setSelectedUser(row)
    setDrawerOpen(true)
    setTxnLoading(true)
    try {
      const res = await http.get<CreditTransaction[]>(
        `/api/v1/admin/credits/${row.user_id}/transactions?limit=50`,
      )
      setTransactions(res.data)
    } catch {
      message.error('加载流水失败')
    } finally {
      setTxnLoading(false)
    }
  }, [message])

  // ── 操作弹窗 ────────────────────────────────────────────────
  const openAction = useCallback((mode: ActionMode, row: UserCreditRow) => {
    setActionMode(mode)
    setActionTarget(row)
    form.resetFields()
    setModalOpen(true)
  }, [form])

  const handleActionOk = useCallback(async () => {
    if (!actionTarget) return
    try {
      const values = await form.validateFields()
      setActionLoading(true)
      if (actionMode === 'topup') {
        await http.post(`/api/v1/admin/credits/${actionTarget.user_id}/topup`, {
          amount: values.amount,
          note: values.note || null,
        })
        message.success(`已为 ${actionTarget.email ?? actionTarget.user_id} 充值 ${values.amount} 积分`)
      } else {
        await http.post(`/api/v1/admin/credits/${actionTarget.user_id}/adjust`, {
          delta: values.delta,
          note: values.note || null,
        })
        const sign = (values.delta ?? 0) > 0 ? '+' : ''
        message.success(`调账成功：${sign}${values.delta} 积分`)
      }
      setModalOpen(false)
      loadList()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail ?? '操作失败')
    } finally {
      setActionLoading(false)
    }
  }, [actionMode, actionTarget, form, message, loadList])

  // ── 表格列定义 ──────────────────────────────────────────────
  const columns: ColumnsType<UserCreditRow> = [
    {
      title: '用户',
      key: 'user',
      render: (_, row) => (
        <div>
          <Text strong>{row.username ?? '—'}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>{row.email ?? row.user_id}</Text>
        </div>
      ),
    },
    {
      title: '余额',
      dataIndex: 'balance',
      sorter: (a, b) => a.balance - b.balance,
      render: (val: number) => {
        const color = val < 100 ? 'red' : val < 1000 ? 'orange' : 'green'
        return <Tag color={color}>{val.toLocaleString()} 积分</Tag>
      },
    },
    {
      title: '累计消耗',
      dataIndex: 'total_consumed',
      render: (val: number) => <Text type="secondary">{val.toLocaleString()}</Text>,
    },
    {
      title: '累计充值',
      dataIndex: 'total_topped_up',
      render: (val: number) => <Text type="secondary">{val.toLocaleString()}</Text>,
    },
    {
      title: '最后更新',
      dataIndex: 'updated_at',
      render: (val: string | null) =>
        val ? new Date(val).toLocaleString('zh-CN') : '—',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, row) => (
        <Space size="small">
          <Button
            size="small"
            icon={<PlusOutlined />}
            type="primary"
            ghost
            onClick={() => openAction('topup', row)}
          >
            充值
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openAction('adjust', row)}
          >
            调账
          </Button>
          <Button
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => openDrawer(row)}
          >
            流水
          </Button>
        </Space>
      ),
    },
  ]

  // ── 流水列定义 ──────────────────────────────────────────────
  const txnColumns: ColumnsType<CreditTransaction> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 130,
      render: (v: string) => new Date(v).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }),
    },
    {
      title: '变动',
      dataIndex: 'delta',
      width: 80,
      render: (v: number) => (
        <Text style={{ color: v > 0 ? '#52c41a' : '#ff4d4f', fontWeight: 600 }}>
          {v > 0 ? `+${v}` : v}
        </Text>
      ),
    },
    {
      title: '余额',
      dataIndex: 'balance_after',
      width: 80,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '来源',
      dataIndex: 'ref_type',
      width: 100,
      render: (v: string) => REF_TYPE_LABEL[v] ?? v,
    },
    {
      title: '模型 / 备注',
      key: 'detail',
      render: (_, row) => (
        <div style={{ fontSize: 12 }}>
          {row.model && <Text type="secondary">{row.model}</Text>}
          {row.prompt_tokens != null && (
            <Text type="secondary"> · in {row.prompt_tokens.toLocaleString()} / out {(row.completion_tokens ?? 0).toLocaleString()} tok</Text>
          )}
          {row.note && <div style={{ color: '#888' }}>{row.note}</div>}
        </div>
      ),
    },
  ]

  // ── 渲染 ─────────────────────────────────────────────────────
  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>用户积分管理</Typography.Title>
        <Button onClick={loadList} loading={loading}>刷新</Button>
      </div>

      <Table
        rowKey="user_id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: true }}
        size="middle"
      />

      {/* 流水 Drawer */}
      <Drawer
        title={selectedUser ? `流水记录 — ${selectedUser.email ?? selectedUser.user_id}` : '流水记录'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={700}
      >
        {selectedUser && (
          <Descriptions size="small" style={{ marginBottom: 16 }}>
            <Descriptions.Item label="当前余额">
              <Tag color={selectedUser.balance < 100 ? 'red' : selectedUser.balance < 1000 ? 'orange' : 'green'}>
                {selectedUser.balance.toLocaleString()} 积分
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="累计消耗">{selectedUser.total_consumed.toLocaleString()}</Descriptions.Item>
            <Descriptions.Item label="累计充值">{selectedUser.total_topped_up.toLocaleString()}</Descriptions.Item>
          </Descriptions>
        )}
        <Table
          rowKey="id"
          columns={txnColumns}
          dataSource={transactions}
          loading={txnLoading}
          pagination={{ pageSize: 20 }}
          size="small"
        />
      </Drawer>

      {/* 充值 / 调账 Modal */}
      <Modal
        title={actionMode === 'topup' ? `充值积分 — ${actionTarget?.email ?? ''}` : `调账 — ${actionTarget?.email ?? ''}`}
        open={modalOpen}
        onOk={handleActionOk}
        onCancel={() => setModalOpen(false)}
        confirmLoading={actionLoading}
        okText={actionMode === 'topup' ? '确认充值' : '确认调账'}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {actionMode === 'topup' ? (
            <Form.Item
              name="amount"
              label="充值积分数"
              rules={[{ required: true, message: '请输入充值积分数' }, { type: 'number', min: 1, message: '必须 > 0' }]}
            >
              <InputNumber style={{ width: '100%' }} min={1} placeholder="例如 10000" />
            </Form.Item>
          ) : (
            <Form.Item
              name="delta"
              label="调整量（正=加分，负=扣分）"
              rules={[{ required: true, message: '请输入调整量' }, { type: 'number', validator: (_, v) => v !== 0 ? Promise.resolve() : Promise.reject('不能为 0') }]}
            >
              <InputNumber style={{ width: '100%' }} placeholder="例如 -500 或 2000" />
            </Form.Item>
          )}
          <Form.Item name="note" label="备注（可选）">
            <Input.TextArea rows={2} placeholder="充值原因或说明" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
