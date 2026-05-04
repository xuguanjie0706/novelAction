import { useCallback, useEffect, useState } from 'react'
import { App, Button, Form, Input, InputNumber, Modal, Space, Switch, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ApiOutlined, PlusOutlined, StarOutlined } from '@ant-design/icons'
import { http } from '../api/http'
import type { LlmProvider, LlmTestConnectionResult } from '../types/llm'

const { Text } = Typography

type FormValues = {
  name: string
  base_url: string
  model_name: string
  api_key?: string
  enabled: boolean
  is_default: boolean
  sort_order: number
}

export default function LlmProvidersPage() {
  const { message, modal } = App.useApp()
  const [rows, setRows] = useState<LlmProvider[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState<LlmProvider | null>(null)
  const [form] = Form.useForm<FormValues>()
  const [testing, setTesting] = useState(false)
  const [testQuickOpen, setTestQuickOpen] = useState(false)
  const [testQuickForm] = Form.useForm<{ base_url: string; model_name: string; api_key?: string }>()
  const [testQuickResult, setTestQuickResult] = useState<LlmTestConnectionResult | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await http.get<LlmProvider[]>('/api/v1/admin/llm-providers/')
      // 只展示文本类提供者（图片类在「图片模型」菜单管理）
      setRows(data.filter(r => !r.provider_type || r.provider_type === 'text'))
    } catch (e: unknown) {
      message.error('加载失败，请确认后端已启动且可访问 /api')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void load()
  }, [load])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({
      enabled: true,
      is_default: false,
      sort_order: 0,
    })
    setOpen(true)
  }

  const openEdit = (row: LlmProvider) => {
    setEditing(row)
    form.setFieldsValue({
      name: row.name,
      base_url: row.base_url,
      model_name: row.model_name,
      api_key: '',
      enabled: row.enabled,
      is_default: row.is_default,
      sort_order: row.sort_order,
    })
    setOpen(true)
  }

  const submit = async () => {
    try {
      const v = await form.validateFields()
      setSaving(true)
      const body: Record<string, unknown> = {
        name: v.name.trim(),
        base_url: v.base_url.trim(),
        model_name: v.model_name.trim(),
        provider_type: 'text',
        enabled: v.enabled,
        is_default: v.is_default,
        sort_order: v.sort_order ?? 0,
      }
      const ak = v.api_key?.trim()
      if (editing) {
        if (ak) body.api_key = ak
      } else if (ak) {
        body.api_key = ak
      }

      if (editing) {
        await http.patch(`/api/v1/admin/llm-providers/${editing.id}`, body)
        message.success('已保存')
      } else {
        await http.post('/api/v1/admin/llm-providers/', body)
        message.success('已创建')
      }
      setOpen(false)
      await load()
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown }).errorFields) return
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const remove = (row: LlmProvider) => {
    modal.confirm({
      title: `删除「${row.name}」？`,
      onOk: async () => {
        await http.delete(`/api/v1/admin/llm-providers/${row.id}`)
        message.success('已删除')
        await load()
      },
    })
  }

  const setDefault = async (row: LlmProvider) => {
    await http.post(`/api/v1/admin/llm-providers/${row.id}/set-default`)
    message.success('已设为默认远程模型')
    await load()
  }

  const showTestResult = (res: LlmTestConnectionResult) => {
    if (res.ok) {
      message.success(
        `${res.message}${res.latency_ms != null ? `（${res.latency_ms} ms）` : ''}`,
        5,
      )
    } else {
      message.error(`${res.message}${res.latency_ms != null ? `（${res.latency_ms} ms）` : ''}`, 8)
    }
  }

  const testSavedRow = async (row: LlmProvider) => {
    setTesting(true)
    try {
      const { data } = await http.post<LlmTestConnectionResult>(
        `/api/v1/admin/llm-providers/${row.id}/test-connection`,
      )
      setTestQuickResult(null)
      showTestResult(data)
    } catch {
      message.error('测试请求失败（网络或后端）')
    } finally {
      setTesting(false)
    }
  }

  const testCurrentModalForm = async () => {
    try {
      await form.validateFields(['base_url', 'model_name'])
      const vals = form.getFieldsValue()
      const base_url = vals.base_url?.trim() ?? ''
      const model_name = vals.model_name?.trim() ?? ''
      const api_key = vals.api_key?.trim()
      setTesting(true)
      let data: LlmTestConnectionResult
      if (editing && !api_key) {
        const r = await http.post<LlmTestConnectionResult>(
          `/api/v1/admin/llm-providers/${editing.id}/test-connection`,
        )
        data = r.data
      } else {
        const r = await http.post<LlmTestConnectionResult>('/api/v1/admin/llm-providers/test-connection', {
          base_url,
          model_name,
          api_key: api_key || undefined,
        })
        data = r.data
      }
      showTestResult(data)
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown }).errorFields) return
      message.error('测试失败')
    } finally {
      setTesting(false)
    }
  }

  const openQuickTest = () => {
    setTestQuickResult(null)
    testQuickForm.resetFields()
    setTestQuickOpen(true)
  }

  const submitQuickTest = async () => {
    try {
      const v = await testQuickForm.validateFields()
      setTesting(true)
      const { data } = await http.post<LlmTestConnectionResult>('/api/v1/admin/llm-providers/test-connection', {
        base_url: v.base_url.trim(),
        model_name: v.model_name.trim(),
        api_key: v.api_key?.trim() || undefined,
      })
      setTestQuickResult(data)
      showTestResult(data)
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown }).errorFields) return
      message.error('测试失败')
    } finally {
      setTesting(false)
    }
  }

  const columns: ColumnsType<LlmProvider> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 160,
      ellipsis: true,
    },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      ellipsis: true,
      render: (t: string) => <Text copyable={{ text: t }}>{t}</Text>,
    },
    {
      title: '模型 ID',
      dataIndex: 'model_name',
      width: 180,
      ellipsis: true,
    },
    {
      title: 'API Key',
      width: 120,
      render: (_, r) => (
        <span>
          {r.has_api_key ? <Tag color="green">已配置</Tag> : <Tag>无</Tag>}
          {r.api_key_hint ? <Text type="secondary"> {r.api_key_hint}</Text> : null}
        </span>
      ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 72,
      render: (v: boolean) => (v ? <Tag color="blue">是</Tag> : <Tag>否</Tag>),
    },
    {
      title: '默认',
      dataIndex: 'is_default',
      width: 72,
      render: (v: boolean) => (v ? <Tag color="gold">默认</Tag> : null),
    },
    {
      title: '排序',
      dataIndex: 'sort_order',
      width: 64,
    },
    {
      title: '操作',
      key: 'actions',
      width: 280,
      fixed: 'right',
      render: (_, row) => (
        <Space size="small" wrap>
          <Button
            type="link"
            size="small"
            icon={<ApiOutlined />}
            loading={testing}
            onClick={() => void testSavedRow(row)}
          >
            测试
          </Button>
          {!row.is_default ? (
            <Button type="link" size="small" icon={<StarOutlined />} onClick={() => void setDefault(row)}>
              设默认
            </Button>
          ) : null}
          <Button type="link" size="small" onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Button type="link" size="small" danger onClick={() => remove(row)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <div>
            <Typography.Title level={4} style={{ margin: 0 }}>
              大模型配置
            </Typography.Title>
            <Text type="secondary">
              创作端选择「Gemini / 远程」时使用<strong>一条启用且标记为默认</strong>的记录；若无则回退环境变量 GEMINI_*。
            </Text>
          </div>
          <Space>
            <Button icon={<ApiOutlined />} onClick={openQuickTest}>
              测试联通
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新增
            </Button>
          </Space>
        </Space>

        <Table<LlmProvider>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={rows}
          scroll={{ x: 1100 }}
          pagination={false}
        />
      </Space>

      <Modal
        title={editing ? '编辑大模型' : '新增大模型'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void submit()}
        confirmLoading={saving}
        destroyOnClose
        width={560}
        footer={(
          <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
            <Button onClick={() => void testCurrentModalForm()} loading={testing} icon={<ApiOutlined />}>
              测试联通（不保存）
            </Button>
            <Button onClick={() => setOpen(false)}>取消</Button>
            <Button type="primary" loading={saving} onClick={() => void submit()}>
              保存
            </Button>
          </Space>
        )}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="显示名称" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="例如：Gemini Flash 免费线路" />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="网关地址"
            rules={[{ required: true, message: '必填' }]}
            extra="可填根路径，后端会自动补 /v1（OpenAI 兼容）"
          >
            <Input placeholder="http://host:3333 或 https://xxx/v1" />
          </Form.Item>
          <Form.Item name="model_name" label="模型 ID" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="例如 gemini-2.5-flash-free" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            extra={
              editing ? '留空表示不修改已有密钥；填空格并保存可在后端改为「清空」（请用下方开关）' : '可选，部分免费网关无需填写'
            }
          >
            <Input.Password placeholder={editing ? '不修改请留空' : '可选'} autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="is_default" label="设为默认远程模型" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="sort_order" label="排序（越小越靠前）">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="测试远程网关联通"
        open={testQuickOpen}
        onCancel={() => setTestQuickOpen(false)}
        onOk={() => void submitQuickTest()}
        confirmLoading={testing}
        okText="发起测试"
        destroyOnClose
        width={520}
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          使用 OpenAI 兼容 <code>/chat/completions</code> 发一条最小请求；密钥仅发往你的后端，由后端转发上游。
        </Text>
        <Form form={testQuickForm} layout="vertical">
          <Form.Item name="base_url" label="网关 Base URL" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="http://host:3333 或已带 /v1 的地址" />
          </Form.Item>
          <Form.Item name="model_name" label="模型 ID" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="例如 gemini-3-flash-free" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key（可选）">
            <Input.Password placeholder="无密钥可留空" autoComplete="new-password" />
          </Form.Item>
        </Form>
        {testQuickResult ? (
          <div
            style={{
              marginTop: 12,
              padding: 12,
              borderRadius: 8,
              background: testQuickResult.ok ? '#f6ffed' : '#fff2f0',
              border: `1px solid ${testQuickResult.ok ? '#b7eb8f' : '#ffccc7'}`,
            }}
          >
            <Text strong>{testQuickResult.ok ? '成功' : '失败'}</Text>
            <div style={{ marginTop: 6, fontSize: 13 }}>{testQuickResult.message}</div>
            {(testQuickResult.latency_ms != null || testQuickResult.http_status != null) && (
              <Text type="secondary" style={{ fontSize: 12, marginTop: 8, display: 'block' }}>
                {testQuickResult.http_status != null ? `HTTP ${testQuickResult.http_status}` : ''}
                {testQuickResult.latency_ms != null ? ` · ${testQuickResult.latency_ms} ms` : ''}
              </Text>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
