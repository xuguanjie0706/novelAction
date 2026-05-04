import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Form,
  Image,
  Input,
  InputNumber,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PictureOutlined, PlusOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { http } from '../api/http'
import type { LlmProvider } from '../types/llm'

const { Text } = Typography

type FormValues = {
  name: string
  base_url: string
  model_name: string
  api_key?: string
  enabled: boolean
  sort_order: number
}

interface TestImageResult {
  ok: boolean
  message: string
  preview_url?: string   // 生成成功时的预览图（data URL 或外链）
  latency_ms?: number
}

export default function ImageProvidersPage() {
  const { message, modal } = App.useApp()
  const [rows, setRows] = useState<LlmProvider[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState<LlmProvider | null>(null)
  const [form] = Form.useForm<FormValues>()

  // 测试弹窗
  const [testOpen, setTestOpen] = useState(false)
  const [testTarget, setTestTarget] = useState<LlmProvider | null>(null)
  const [testResult, setTestResult] = useState<TestImageResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [testPrompt, setTestPrompt] = useState('A beautiful sunset over a mountain lake, digital art')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await http.get<LlmProvider[]>('/api/v1/admin/llm-providers/')
      setRows(data.filter(r => r.provider_type === 'image'))
    } catch {
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
    form.setFieldsValue({ enabled: true, sort_order: 0 })
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
        provider_type: 'image',   // 固定为图片类
        enabled: v.enabled,
        is_default: false,        // 图片提供者无默认概念
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

  // 测试：向后端发一张最小生成请求，看是否联通
  const openTest = (row: LlmProvider) => {
    setTestTarget(row)
    setTestResult(null)
    setTestOpen(true)
  }

  const runTest = async () => {
    if (!testTarget) return
    setTesting(true)
    setTestResult(null)
    try {
      // 借用封面生成接口：发一张 256x256（部分 provider 不支持小尺寸，fallback 1024x1024）
      // 先用一个极简 prompt 生成，成功即联通
      const t0 = performance.now()
      const res = await http.post<{ data_url?: string; image_url?: string }>(
        // 需要一个已有项目 id，这里我们发自定义测试接口 ——
        // 复用 admin test-connection 接口（后端 cover.py 没有 standalone 测试端点）
        // 实际调用 admin/llm-providers/{id}/test-image
        `/api/v1/admin/llm-providers/${testTarget.id}/test-image`,
        { prompt: testPrompt.trim() || 'A simple test image, minimal' },
      )
      const ms = Math.round(performance.now() - t0)
      const url = res.data.data_url ?? res.data.image_url
      setTestResult({ ok: true, message: '图片生成成功，联通正常', preview_url: url, latency_ms: ms })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setTestResult({ ok: false, message: detail || '生成失败，请检查 base_url / model_name / api_key' })
    } finally {
      setTesting(false)
    }
  }

  const columns: ColumnsType<LlmProvider> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 180,
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
      width: 200,
      ellipsis: true,
      render: (t: string) => <Text code copyable={{ text: t }}>{t}</Text>,
    },
    {
      title: 'API Key',
      width: 120,
      render: (_: unknown, r: LlmProvider) => (
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
      title: '排序',
      dataIndex: 'sort_order',
      width: 64,
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_: unknown, row: LlmProvider) => (
        <Space size="small" wrap>
          <Button
            type="link"
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={() => openTest(row)}
          >
            测试
          </Button>
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
              图片模型配置
            </Typography.Title>
            <Text type="secondary">
              管理用于 AI 封面生成的图片模型（兼容 OpenAI <code>/v1/images/generations</code> 协议），
              例如 DALL·E 3、Flux、Stable Diffusion 等。创作端可在封面弹窗中选择这里配置的模型。
            </Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增图片模型
          </Button>
        </Space>

        <Alert
          type="info"
          showIcon
          message="协议说明"
          description={
            <span>
              图片模型需兼容 OpenAI <code>POST /v1/images/generations</code> 接口格式，
              请求体包含 <code>model</code>、<code>prompt</code>、<code>size</code>、<code>n</code>、
              <code>response_format</code>（支持 <code>b64_json</code> 或 <code>url</code>）。
              常见兼容实现：OpenAI DALL·E、硅基流动 Flux、ComfyUI API 等。
            </span>
          }
          style={{ marginBottom: 4 }}
        />

        <Table<LlmProvider>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={rows}
          scroll={{ x: 900 }}
          pagination={false}
          locale={{ emptyText: '暂无图片模型，点击右上角「新增」添加' }}
        />
      </Space>

      {/* 新增 / 编辑弹窗 */}
      <Modal
        title={editing ? '编辑图片模型' : '新增图片模型'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void submit()}
        confirmLoading={saving}
        destroyOnClose
        width={560}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="显示名称" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="例如：DALL·E 3 官方、硅基 Flux Dev" />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="网关地址（Base URL）"
            rules={[{ required: true, message: '必填' }]}
            extra="填写根路径，后端会自动拼接 /v1/images/generations"
          >
            <Input placeholder="https://api.openai.com 或 https://api.siliconflow.cn" />
          </Form.Item>
          <Form.Item
            name="model_name"
            label="模型 ID"
            rules={[{ required: true, message: '必填' }]}
            extra="传给 images/generations 的 model 字段"
          >
            <Input placeholder="例如 dall-e-3、black-forest-labs/FLUX.1-schnell" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            extra={editing ? '留空表示不修改已有密钥' : '可选，部分免费接口无需填写'}
          >
            <Input.Password
              placeholder={editing ? '不修改请留空' : '可选'}
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="sort_order" label="排序（越小越靠前）">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 测试弹窗 */}
      <Modal
        title={
          <Space>
            <PictureOutlined />
            测试图片生成 — {testTarget?.name}
          </Space>
        }
        open={testOpen}
        onCancel={() => setTestOpen(false)}
        onOk={() => void runTest()}
        confirmLoading={testing}
        okText="发起生成测试"
        destroyOnClose
        width={600}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Text type="secondary">
            向该提供者发一次真实的图片生成请求（1024×1024，1 张），用于验证接口联通与鉴权是否正常。
          </Text>

          <div>
            <div style={{ marginBottom: 6, fontWeight: 500, fontSize: 13 }}>测试 Prompt</div>
            <Input.TextArea
              value={testPrompt}
              onChange={e => setTestPrompt(e.target.value)}
              rows={2}
              placeholder="输入英文描述词，例如 A beautiful mountain at sunset"
            />
          </div>

          {testResult && (
            <div
              style={{
                padding: 16,
                borderRadius: 10,
                border: `1px solid ${testResult.ok ? '#b7eb8f' : '#ffccc7'}`,
                background: testResult.ok ? '#f6ffed' : '#fff2f0',
              }}
            >
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                  <Tag color={testResult.ok ? 'success' : 'error'}>
                    {testResult.ok ? '成功' : '失败'}
                  </Tag>
                  <Text style={{ fontSize: 13 }}>{testResult.message}</Text>
                  {testResult.latency_ms != null && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {testResult.latency_ms} ms
                    </Text>
                  )}
                </Space>

                {testResult.preview_url && (
                  <div style={{ marginTop: 8, textAlign: 'center' }}>
                    <Image
                      src={testResult.preview_url}
                      alt="生成预览"
                      style={{
                        maxWidth: '100%',
                        maxHeight: 320,
                        borderRadius: 8,
                        boxShadow: '0 2px 12px rgba(0,0,0,0.15)',
                      }}
                    />
                  </div>
                )}
              </Space>
            </div>
          )}
        </Space>
      </Modal>
    </div>
  )
}
