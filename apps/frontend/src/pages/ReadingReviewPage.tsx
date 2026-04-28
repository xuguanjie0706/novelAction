import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Form,
  Input,
  List,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { http } from '../api/http'
import type { LlmOverview } from '../types/llm'
import type {
  ChapterCoherenceResult,
  CoherenceReportRecord,
  ModelProfile,
  QualityReport,
  ReviewChapter,
  ReviewProject,
} from '../types/review'

const CHECK_TYPES = ['plot', 'character', 'setting_consistency', 'pacing', 'hooks', 'outline_alignment']

const CHECK_LABELS: Record<string, string> = {
  plot: '情节推进',
  character: '人物一致',
  setting_consistency: '设定一致',
  pacing: '节奏控制',
  hooks: '悬念钩子',
  outline_alignment: '大纲匹配度',
}

const SCORE_COLORS = [
  { min: 85, color: 'green', text: '优秀' },
  { min: 70, color: 'blue', text: '通过' },
  { min: 50, color: 'orange', text: '警告' },
  { min: 0, color: 'red', text: '高风险' },
]

function scoreTag(score: number | undefined) {
  if (score == null) return <Tag>未评测</Tag>
  const matched = SCORE_COLORS.find((item) => score >= item.min) ?? SCORE_COLORS[SCORE_COLORS.length - 1]
  return <Tag color={matched.color}>{matched.text} {score}</Tag>
}

export default function ReadingReviewPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [projects, setProjects] = useState<ReviewProject[]>([])
  const [projectId, setProjectId] = useState<string>()
  const [chapters, setChapters] = useState<ReviewChapter[]>([])
  const [llmOverview, setLlmOverview] = useState<LlmOverview | null>(null)
  const [selectedModelOption, setSelectedModelOption] = useState<string>('local')

  const [selectedChapterId, setSelectedChapterId] = useState<string>()
  const [qualityLoading, setQualityLoading] = useState(false)
  const [qualityReport, setQualityReport] = useState<QualityReport | null>(null)

  const [coherenceLoading, setCoherenceLoading] = useState(false)
  const [selectedCoherenceChapters, setSelectedCoherenceChapters] = useState<string[]>([])
  const [coherenceResult, setCoherenceResult] = useState<ChapterCoherenceResult | null>(null)
  const [saveLoading, setSaveLoading] = useState(false)
  const [reportNameForm] = Form.useForm<{ name: string }>()

  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyRows, setHistoryRows] = useState<CoherenceReportRecord[]>([])
  const [compareIds, setCompareIds] = useState<string[]>([])

  const loadProjects = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await http.get<ReviewProject[]>('/api/v1/projects/')
      setProjects(data)
      if (!projectId && data.length > 0) setProjectId(data[0].id)
    } catch {
      message.error('加载项目失败，请确认后端服务可用')
    } finally {
      setLoading(false)
    }
  }, [message, projectId])

  const loadLlmOverview = useCallback(async () => {
    try {
      const { data } = await http.get<LlmOverview>('/api/v1/llm/overview')
      setLlmOverview(data)
      if (data.remote_providers.length > 0) {
        const defaultProvider = data.remote_providers.find((p) => p.is_default)
        if (!selectedModelOption || selectedModelOption === 'local') {
          setSelectedModelOption(defaultProvider ? `provider:${defaultProvider.id}` : 'local')
        }
      } else {
        setSelectedModelOption('local')
      }
    } catch {
      setSelectedModelOption('local')
      message.warning('模型列表获取失败，已回退为本地模型')
    }
  }, [message, selectedModelOption])

  const loadChapters = useCallback(async (pid: string) => {
    try {
      const { data } = await http.get<ReviewChapter[]>(`/api/v1/projects/${pid}/chapters/`)
      setChapters(data)
      if (data.length > 0) {
        setSelectedChapterId(data[0].id)
      } else {
        setSelectedChapterId(undefined)
      }
    } catch {
      message.error('加载章节失败')
    }
  }, [message])

  const loadHistory = useCallback(async (pid: string) => {
    setHistoryLoading(true)
    try {
      const { data } = await http.get<CoherenceReportRecord[]>(`/api/v1/projects/${pid}/ai/chapter-coherence-reports`, {
        params: { limit: 30 },
      })
      setHistoryRows(data)
    } catch {
      message.error('加载历史报告失败')
    } finally {
      setHistoryLoading(false)
    }
  }, [message])

  useEffect(() => {
    void loadProjects()
    void loadLlmOverview()
  }, [loadProjects, loadLlmOverview])

  const selectedProviderId = selectedModelOption.startsWith('provider:')
    ? selectedModelOption.replace('provider:', '')
    : undefined
  const modelProfile: ModelProfile = selectedProviderId ? 'gemini' : 'local'

  useEffect(() => {
    if (!projectId) return
    setQualityReport(null)
    setCoherenceResult(null)
    setSelectedCoherenceChapters([])
    setCompareIds([])
    void loadChapters(projectId)
    void loadHistory(projectId)
  }, [projectId, loadChapters, loadHistory])

  const runQualityCheck = async () => {
    if (!projectId || !selectedChapterId) {
      message.warning('请先选择项目与章节')
      return
    }
    setQualityLoading(true)
    try {
      const { data } = await http.post<QualityReport>(`/api/v1/projects/${projectId}/ai/quality-check`, {
        chapter_id: selectedChapterId,
        model_profile: modelProfile,
        check_types: CHECK_TYPES,
        llm_provider_id: selectedProviderId,
      })
      setQualityReport(data)
      message.success('单章评测完成')
      await loadChapters(projectId)
    } catch {
      message.error('单章评测失败')
    } finally {
      setQualityLoading(false)
    }
  }

  const runCoherenceCheck = async () => {
    if (!projectId) {
      message.warning('请先选择项目')
      return
    }
    if (selectedCoherenceChapters.length < 2) {
      message.warning('至少选择 2 章进行连贯性评测')
      return
    }
    setCoherenceLoading(true)
    try {
      const { data } = await http.post<ChapterCoherenceResult>(
        `/api/v1/projects/${projectId}/ai/chapter-coherence-check`,
        {
          chapter_ids: selectedCoherenceChapters,
          model_profile: modelProfile,
          llm_provider_id: selectedProviderId,
        },
      )
      setCoherenceResult(data)
      message.success('连贯性评测完成')
    } catch {
      message.error('连贯性评测失败')
    } finally {
      setCoherenceLoading(false)
    }
  }

  const saveCoherenceReport = async () => {
    if (!projectId || !coherenceResult) {
      message.warning('请先完成一次连贯性评测')
      return
    }
    const values = await reportNameForm.validateFields().catch(() => null)
    if (!values) return
    setSaveLoading(true)
    try {
      await http.post(`/api/v1/projects/${projectId}/ai/chapter-coherence-reports`, {
        name: values.name.trim() || undefined,
        model_profile: modelProfile,
        selected_chapter_ids: selectedCoherenceChapters,
        result: coherenceResult,
      })
      message.success('连贯性报告已保存')
      reportNameForm.resetFields()
      await loadHistory(projectId)
    } catch {
      message.error('保存报告失败')
    } finally {
      setSaveLoading(false)
    }
  }

  const chapterOptions = useMemo(
    () =>
      chapters.map((c) => ({
        label: `第${c.sort_order + 1}章 · ${c.title || '未命名'}${c.last_quality_score != null ? `（${c.last_quality_score}分）` : ''}`,
        value: c.id,
      })),
    [chapters],
  )

  const chapterColumns: ColumnsType<ReviewChapter> = [
    {
      title: '章节',
      dataIndex: 'title',
      render: (_, row) => `第${row.sort_order + 1}章 · ${row.title || '未命名'}`,
    },
    {
      title: '最近评分',
      dataIndex: 'last_quality_score',
      width: 150,
      render: (v: number | undefined) => scoreTag(v),
    },
  ]

  const overviewScored = chapters.filter((c) => c.last_quality_score != null)
  const overviewAvg = overviewScored.length
    ? Math.round(
      overviewScored.reduce((sum, c) => sum + Number(c.last_quality_score ?? 0), 0) / overviewScored.length,
    )
    : undefined
  const lowCount = chapters.filter((c) => Number(c.last_quality_score ?? 100) < 70).length
  const outlineRiskChapters = chapters
    .map((c) => {
      const outlineScore = c.last_quality_report?.dimensions?.outline_alignment?.score
      return {
        id: c.id,
        title: c.title || '未命名',
        chapterNo: c.sort_order + 1,
        score: outlineScore,
      }
    })
    .filter((item) => item.score != null && Number(item.score) < 70)
    .sort((a, b) => Number(a.score) - Number(b.score))

  const compareRows = historyRows.filter((row) => compareIds.includes(row.id))
  const compareA = compareRows[0]
  const compareB = compareRows[1]

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          小说阅读评测
        </Typography.Title>
        <Space wrap>
          <Select
            style={{ minWidth: 240 }}
            placeholder="选择项目"
            options={projects.map((p) => ({ value: p.id, label: p.title }))}
            value={projectId}
            loading={loading}
            onChange={setProjectId}
          />
          <Select<string>
            style={{ width: 340 }}
            value={selectedModelOption}
            options={[
              {
                label: `本地 · ${llmOverview?.local_model_name ?? 'default'}`,
                value: 'local',
              },
              ...(llmOverview?.remote_providers ?? []).map((p) => ({
                label: `远程 · ${p.name} (${p.model_name})${p.is_default ? ' [默认]' : ''}`,
                value: `provider:${p.id}`,
              })),
            ]}
            onChange={setSelectedModelOption}
          />
        </Space>
      </Space>

      <Tabs
        items={[
          {
            key: 'overview',
            label: '总览',
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Row gutter={16}>
                  <Col span={8}>
                    <Card><Statistic title="章节总数" value={chapters.length} /></Card>
                  </Col>
                  <Col span={8}>
                    <Card><Statistic title="平均分（已评测）" value={overviewAvg ?? '-'} /></Card>
                  </Col>
                  <Col span={8}>
                    <Card><Statistic title="低分章节（<70）" value={lowCount} /></Card>
                  </Col>
                </Row>
                <Card title="章节评分概览">
                  <Table<ReviewChapter>
                    size="small"
                    rowKey="id"
                    pagination={false}
                    columns={chapterColumns}
                    dataSource={chapters}
                    locale={{ emptyText: <Empty description="暂无章节，先在创作端生成章节" /> }}
                  />
                </Card>
                <Card title="偏纲风险章节（大纲匹配度 < 70）">
                  {outlineRiskChapters.length === 0 ? (
                    <Empty description="当前暂无偏纲风险章节（或尚未产生大纲匹配度历史数据）" />
                  ) : (
                    <List
                      dataSource={outlineRiskChapters}
                      renderItem={(item) => (
                        <List.Item>
                          <Space>
                            <Tag color="red">第{item.chapterNo}章</Tag>
                            <span>{item.title}</span>
                            <Tag color="orange">大纲匹配度：{item.score}</Tag>
                          </Space>
                        </List.Item>
                      )}
                    />
                  )}
                </Card>
              </Space>
            ),
          },
          {
            key: 'chapter',
            label: '单章评测',
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Space wrap>
                  <Select
                    style={{ minWidth: 420 }}
                    placeholder="选择章节"
                    options={chapterOptions}
                    value={selectedChapterId}
                    onChange={setSelectedChapterId}
                  />
                  <Button type="primary" loading={qualityLoading} onClick={() => void runQualityCheck()}>
                    开始评测
                  </Button>
                </Space>
                {!qualityReport ? (
                  <Card><Empty description="尚未评测，选择章节后点击开始评测" /></Card>
                ) : (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Card title={`总分：${qualityReport.overall_score ?? '-'} 分`}>
                      <Space wrap>
                        {Object.entries(qualityReport.dimensions || {}).map(([key, val]) => (
                          <Tag key={key} color={val.status === 'fail' ? 'red' : val.status === 'warning' ? 'orange' : 'blue'}>
                            {CHECK_LABELS[key] ?? key}：{val.score}
                          </Tag>
                        ))}
                      </Space>
                      {qualityReport.dimensions?.outline_alignment ? (
                        <Card
                          size="small"
                          style={{ marginTop: 12, background: '#fff7e6', borderColor: '#ffd591' }}
                          title="大纲匹配度专项"
                        >
                          <Space wrap>
                            {scoreTag(qualityReport.dimensions.outline_alignment.score)}
                            <Typography.Text>{qualityReport.dimensions.outline_alignment.comment}</Typography.Text>
                          </Space>
                        </Card>
                      ) : null}
                      <Typography.Paragraph style={{ marginTop: 12, marginBottom: 0 }}>
                        {qualityReport.summary || '暂无总结'}
                      </Typography.Paragraph>
                    </Card>
                    <Card title="问题清单">
                      <List
                        dataSource={qualityReport.issues || []}
                        locale={{ emptyText: '未发现明显问题' }}
                        renderItem={(item) => (
                          <List.Item>
                            <Space>
                              <Tag color={item.type === 'warning' ? 'orange' : 'red'}>{item.type}</Tag>
                              <span>{item.description}</span>
                            </Space>
                          </List.Item>
                        )}
                      />
                    </Card>
                    <Card title="修改建议">
                      <List
                        dataSource={qualityReport.suggestions || []}
                        locale={{ emptyText: '暂无建议' }}
                        renderItem={(item) => <List.Item>{item}</List.Item>}
                      />
                    </Card>
                  </Space>
                )}
              </Space>
            ),
          },
          {
            key: 'coherence',
            label: '连贯性评测',
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Card title="选择章节范围">
                  <Space direction="vertical" style={{ width: '100%' }} size="middle">
                    <Space>
                      <Button onClick={() => setSelectedCoherenceChapters(chapters.slice(-3).map((c) => c.id))}>最近3章</Button>
                      <Button onClick={() => setSelectedCoherenceChapters(chapters.slice(-5).map((c) => c.id))}>最近5章</Button>
                      <Button onClick={() => setSelectedCoherenceChapters(chapters.slice(-10).map((c) => c.id))}>最近10章</Button>
                    </Space>
                    <Checkbox.Group
                      style={{ width: '100%' }}
                      value={selectedCoherenceChapters}
                      onChange={(vals) => setSelectedCoherenceChapters(vals as string[])}
                    >
                      <Row gutter={[12, 12]}>
                        {chapters.map((c) => (
                          <Col key={c.id} span={8}>
                            <Checkbox value={c.id}>第{c.sort_order + 1}章 · {c.title || '未命名'}</Checkbox>
                          </Col>
                        ))}
                      </Row>
                    </Checkbox.Group>
                    <Button type="primary" loading={coherenceLoading} onClick={() => void runCoherenceCheck()}>
                      开始连贯性评测
                    </Button>
                  </Space>
                </Card>

                {coherenceResult ? (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Card title="评测结果">
                      <Space wrap>
                        <Tag color="blue">总分：{coherenceResult.overall_score}</Tag>
                        <Tag color="geekblue">标题匹配：{coherenceResult.title_match_score}</Tag>
                        <Tag color="purple">跨章连贯：{coherenceResult.continuity_score}</Tag>
                      </Space>
                      <Typography.Paragraph style={{ marginTop: 12, marginBottom: 0 }}>
                        {coherenceResult.summary || '暂无总结'}
                      </Typography.Paragraph>
                    </Card>
                    <Card title="跨章风险">
                      <List
                        dataSource={coherenceResult.cross_chapter_issues || []}
                        locale={{ emptyText: '未发现明显跨章风险' }}
                        renderItem={(item) => (
                          <List.Item>
                            <Space>
                              <Tag color={item.severity === 'warning' ? 'orange' : 'red'}>{item.type}</Tag>
                              <span>{item.description}</span>
                            </Space>
                          </List.Item>
                        )}
                      />
                    </Card>
                    <Card title="保存报告">
                      <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Form form={reportNameForm} layout="inline">
                          <Form.Item
                            name="name"
                            label="报告名称"
                            rules={[{ required: true, message: '请输入报告名称' }]}
                          >
                            <Input style={{ width: 320 }} placeholder="例如：前10章连贯性巡检" />
                          </Form.Item>
                        </Form>
                        <Button type="primary" loading={saveLoading} onClick={() => void saveCoherenceReport()}>
                          保存到历史
                        </Button>
                      </Space>
                    </Card>
                  </Space>
                ) : null}
              </Space>
            ),
          },
          {
            key: 'history',
            label: '历史记录',
            children: (
              <Card>
                {compareA && compareB ? (
                  <Card
                    size="small"
                    style={{ marginBottom: 16, background: '#f6ffed', borderColor: '#b7eb8f' }}
                    title="报告对比（本次 vs 上次）"
                  >
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Typography.Text>
                        {compareA.name}（{compareA.result?.overall_score ?? '-'}） vs {compareB.name}（{compareB.result?.overall_score ?? '-'}）
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        分差：{Number((compareA.result?.overall_score ?? 0) - (compareB.result?.overall_score ?? 0)).toFixed(1)}
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        标题匹配分差：{Number((compareA.result?.title_match_score ?? 0) - (compareB.result?.title_match_score ?? 0)).toFixed(1)}
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        连贯性分差：{Number((compareA.result?.continuity_score ?? 0) - (compareB.result?.continuity_score ?? 0)).toFixed(1)}
                      </Typography.Text>
                    </Space>
                  </Card>
                ) : null}
                <Table<CoherenceReportRecord>
                  rowKey="id"
                  loading={historyLoading}
                  dataSource={historyRows}
                  pagination={{ pageSize: 10 }}
                  rowSelection={{
                    selectedRowKeys: compareIds,
                    onChange: (keys) => setCompareIds((keys as string[]).slice(-2)),
                  }}
                  columns={[
                    { title: '报告名', dataIndex: 'name' },
                    { title: '模型', dataIndex: 'model_profile', width: 120 },
                    {
                      title: '章节数',
                      width: 100,
                      render: (_, row) => row.selected_chapter_ids?.length ?? 0,
                    },
                    {
                      title: '总分',
                      width: 100,
                      render: (_, row) => row.result?.overall_score ?? '-',
                    },
                    {
                      title: '创建时间',
                      dataIndex: 'created_at',
                      width: 220,
                    },
                  ]}
                  expandable={{
                    expandedRowRender: (row) => (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Typography.Text type="secondary">{row.result?.summary || '暂无总结'}</Typography.Text>
                        <List
                          size="small"
                          header="建议"
                          dataSource={row.result?.suggestions || []}
                          locale={{ emptyText: '暂无建议' }}
                          renderItem={(item) => <List.Item>{item}</List.Item>}
                        />
                      </Space>
                    ),
                  }}
                  locale={{ emptyText: <Empty description="暂无历史报告" /> }}
                />
              </Card>
            ),
          },
        ]}
      />
    </Space>
  )
}
