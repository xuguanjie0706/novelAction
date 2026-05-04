import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  List,
  Modal,
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
import { useNavigate } from 'react-router-dom'
import { http } from '../api/http'
import type { LlmOverview } from '../types/llm'
import type {
  ChapterCoherenceResult,
  CoherenceApplyPreviewResponse,
  CoherenceApplyRevisionPreview,
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
  const navigate = useNavigate()
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
  const [rangeStartId, setRangeStartId] = useState<string>()
  const [rangeEndId, setRangeEndId] = useState<string>()
  const [anchorChapterId, setAnchorChapterId] = useState<string>()
  const [coherenceResult, setCoherenceResult] = useState<ChapterCoherenceResult | null>(null)
  const [saveLoading, setSaveLoading] = useState(false)

  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyRows, setHistoryRows] = useState<CoherenceReportRecord[]>([])
  const [coherenceApplyModalOpen, setCoherenceApplyModalOpen] = useState(false)
  const [coherenceApplyReportId, setCoherenceApplyReportId] = useState<string | null>(null)
  const [coherenceApplyRevisions, setCoherenceApplyRevisions] = useState<CoherenceApplyRevisionPreview[]>([])
  const [coherenceApplyLoadingId, setCoherenceApplyLoadingId] = useState<string | null>(null)
  const [coherenceApplyCommitting, setCoherenceApplyCommitting] = useState(false)
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

  const runCoherenceApplyPreview = useCallback(
    async (row: CoherenceReportRecord) => {
      if (!projectId) return
      setCoherenceApplyLoadingId(row.id)
      try {
        const { data } = await http.post<CoherenceApplyPreviewResponse>(
          `/api/v1/projects/${projectId}/ai/chapter-coherence-apply/preview`,
          {
            report_id: row.id,
            model_profile: modelProfile,
            llm_provider_id: selectedProviderId,
          },
        )
        setCoherenceApplyReportId(data.report_id)
        setCoherenceApplyRevisions(data.revisions ?? [])
        setCoherenceApplyModalOpen(true)
      } catch {
        message.error('修订预览生成失败')
      } finally {
        setCoherenceApplyLoadingId(null)
      }
    },
    [message, modelProfile, projectId, selectedProviderId],
  )

  const commitCoherenceApply = useCallback(async () => {
    if (!projectId || !coherenceApplyReportId) return
    const payload = coherenceApplyRevisions.filter((r) => !r.unchanged && r.revised_content.trim())
    if (payload.length === 0) {
      message.warning('预览中无可写入的修订')
      return
    }
    setCoherenceApplyCommitting(true)
    try {
      await http.post(`/api/v1/projects/${projectId}/ai/chapter-coherence-apply/commit`, {
        report_id: coherenceApplyReportId,
        revisions: payload.map((r) => ({ chapter_id: r.chapter_id, revised_content: r.revised_content })),
      })
      message.success('已写入正文')
      setCoherenceApplyModalOpen(false)
      setCoherenceApplyRevisions([])
      setCoherenceApplyReportId(null)
      await loadChapters(projectId)
    } catch {
      message.error('写入失败')
    } finally {
      setCoherenceApplyCommitting(false)
    }
  }, [coherenceApplyReportId, coherenceApplyRevisions, loadChapters, message, projectId])

  useEffect(() => {
    if (!projectId) return
    setQualityReport(null)
    setCoherenceResult(null)
    setSelectedCoherenceChapters([])
    setRangeStartId(undefined)
    setRangeEndId(undefined)
    setAnchorChapterId(undefined)
    setCompareIds([])
    void loadChapters(projectId)
    void loadHistory(projectId)
  }, [projectId, loadChapters, loadHistory])

  useEffect(() => {
    if (chapters.length === 0) return
    if (!rangeStartId) setRangeStartId(chapters[0].id)
    if (!rangeEndId) setRangeEndId(chapters[Math.min(chapters.length - 1, 9)].id)
    if (!anchorChapterId) setAnchorChapterId(chapters[Math.min(chapters.length - 1, 9)].id)
    if (selectedCoherenceChapters.length === 0) {
      setSelectedCoherenceChapters(chapters.slice(0, 10).map((c) => c.id))
    }
  }, [anchorChapterId, chapters, rangeEndId, rangeStartId, selectedCoherenceChapters.length])

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
      if (data.error) {
        setQualityReport(null)
        message.error(`单章评测失败：${data.error}`)
        return
      }
      setQualityReport(data)
      message.success('单章评测完成')
      await loadChapters(projectId)
    } catch {
      message.error('单章评测失败')
    } finally {
      setQualityLoading(false)
    }
  }

  const saveCoherenceReport = useCallback(async (result: ChapterCoherenceResult) => {
    if (!projectId) return
    setSaveLoading(true)
    try {
      const selectedNos = chapters
        .filter((c) => selectedCoherenceChapters.includes(c.id))
        .map((c) => c.sort_order + 1)
        .sort((a, b) => a - b)
      const chapterRangeText = selectedNos.length > 0
        ? selectedNos[0] === selectedNos[selectedNos.length - 1]
          ? `${selectedNos[0]}章`
          : `${selectedNos[0]}-${selectedNos[selectedNos.length - 1]}章`
        : `${selectedCoherenceChapters.length}章`
      const projectTitle = projects.find((p) => p.id === projectId)?.title || '未命名小说'
      await http.post(`/api/v1/projects/${projectId}/ai/chapter-coherence-reports`, {
        name: `${projectTitle}｜${chapterRangeText}`,
        model_profile: modelProfile,
        selected_chapter_ids: selectedCoherenceChapters,
        result,
      })
      await loadHistory(projectId)
      message.success('连贯性评测完成并已自动保存')
    } catch {
      message.warning('连贯性评测完成，但自动保存失败，可稍后重试')
    } finally {
      setSaveLoading(false)
    }
  }, [chapters, loadHistory, message, modelProfile, projectId, projects, selectedCoherenceChapters])

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
      if (data.error) {
        setCoherenceResult(null)
        message.error(`连贯性评测失败：${data.error}`)
        return
      }
      setCoherenceResult(data)
      await saveCoherenceReport(data)
    } catch {
      message.error('连贯性评测失败')
    } finally {
      setCoherenceLoading(false)
    }
  }

  const applyContinuousRange = useCallback((startId?: string, endId?: string) => {
    if (!startId || !endId) return
    const startIndex = chapters.findIndex((c) => c.id === startId)
    const endIndex = chapters.findIndex((c) => c.id === endId)
    if (startIndex < 0 || endIndex < 0) return
    const [from, to] = startIndex <= endIndex ? [startIndex, endIndex] : [endIndex, startIndex]
    setSelectedCoherenceChapters(chapters.slice(from, to + 1).map((c) => c.id))
  }, [chapters])

  const applyAnchorWindow = useCallback((size: number, direction: 'prev' | 'next') => {
    if (!anchorChapterId) return
    const anchorIndex = chapters.findIndex((c) => c.id === anchorChapterId)
    if (anchorIndex < 0) return
    const from = direction === 'prev' ? Math.max(0, anchorIndex - size + 1) : anchorIndex
    const to = direction === 'prev' ? anchorIndex : Math.min(chapters.length - 1, anchorIndex + size - 1)
    setRangeStartId(chapters[from]?.id)
    setRangeEndId(chapters[to]?.id)
    setSelectedCoherenceChapters(chapters.slice(from, to + 1).map((c) => c.id))
  }, [anchorChapterId, chapters])

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
  const selectedCoherenceChapterNos = chapters
    .filter((c) => selectedCoherenceChapters.includes(c.id))
    .map((c) => c.sort_order + 1)
    .sort((a, b) => a - b)
  const selectedRangeHint = selectedCoherenceChapterNos.length
    ? `第${selectedCoherenceChapterNos[0]}章 ~ 第${selectedCoherenceChapterNos[selectedCoherenceChapterNos.length - 1]}章`
    : '尚未选择章节'
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
                  <Button
                    onClick={() => {
                      if (!projectId || !selectedChapterId) {
                        message.warning('请先选择项目与章节')
                        return
                      }
                      navigate(`/novels?projectId=${projectId}&chapterId=${selectedChapterId}`)
                    }}
                  >
                    查看正文
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
                    <Space wrap>
                      <Select
                        style={{ width: 260 }}
                        placeholder="起始章节"
                        options={chapterOptions}
                        value={rangeStartId}
                        onChange={(val) => {
                          setRangeStartId(val)
                          applyContinuousRange(val, rangeEndId)
                        }}
                      />
                      <Select
                        style={{ width: 260 }}
                        placeholder="结束章节"
                        options={chapterOptions}
                        value={rangeEndId}
                        onChange={(val) => {
                          setRangeEndId(val)
                          applyContinuousRange(rangeStartId, val)
                        }}
                      />
                      <Button onClick={() => applyContinuousRange(rangeStartId, rangeEndId)}>应用连续范围</Button>
                    </Space>
                    <Space wrap>
                      <Select
                        style={{ width: 260 }}
                        placeholder="先选一个锚点章节"
                        options={chapterOptions}
                        value={anchorChapterId}
                        onChange={setAnchorChapterId}
                      />
                      <Button onClick={() => applyAnchorWindow(3, 'prev')}>选中该章及前2章</Button>
                      <Button onClick={() => applyAnchorWindow(5, 'prev')}>选中该章及前4章</Button>
                      <Button onClick={() => applyAnchorWindow(10, 'prev')}>选中该章及前9章</Button>
                      <Button onClick={() => applyAnchorWindow(3, 'next')}>选中该章及后2章</Button>
                      <Button onClick={() => applyAnchorWindow(5, 'next')}>选中该章及后4章</Button>
                      <Button onClick={() => applyAnchorWindow(10, 'next')}>选中该章及后9章</Button>
                    </Space>
                    <Typography.Text type="secondary">
                      已选 {selectedCoherenceChapters.length} 章（{selectedRangeHint}）
                    </Typography.Text>
                    <div
                      style={{
                        maxHeight: 280,
                        overflowY: 'auto',
                        padding: 12,
                        border: '1px solid #f0f0f0',
                        borderRadius: 8,
                        background: '#fafafa',
                      }}
                    >
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
                    </div>
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
                    <Card title="保存状态">
                      <Typography.Text type={saveLoading ? 'secondary' : 'success'}>
                        {saveLoading ? '正在自动保存报告...' : '评测结果已自动保存到历史记录'}
                      </Typography.Text>
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
                        <Space wrap>
                          <Button
                            type="primary"
                            size="small"
                            loading={coherenceApplyLoadingId === row.id}
                            disabled={!!row.result?.error}
                            onClick={() => void runCoherenceApplyPreview(row)}
                          >
                            根据本评测改正文
                          </Button>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            按评测结论做最小幅度修改并预览，确认后再写入数据库（自动打修订前快照）。
                          </Typography.Text>
                        </Space>
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
      <Modal
        title="连贯性修订预览"
        open={coherenceApplyModalOpen}
        onCancel={() => {
          setCoherenceApplyModalOpen(false)
          setCoherenceApplyRevisions([])
          setCoherenceApplyReportId(null)
        }}
        width={720}
        footer={[
          <Button
            key="cancel"
            onClick={() => {
              setCoherenceApplyModalOpen(false)
              setCoherenceApplyRevisions([])
              setCoherenceApplyReportId(null)
            }}
          >
            取消
          </Button>,
          <Button
            key="ok"
            type="primary"
            loading={coherenceApplyCommitting}
            disabled={coherenceApplyRevisions.every((r) => r.unchanged || !r.revised_content.trim())}
            onClick={() => void commitCoherenceApply()}
          >
            写入数据库
          </Button>,
        ]}
      >
        <List
          size="small"
          dataSource={coherenceApplyRevisions}
          locale={{ emptyText: '暂无预览数据' }}
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space wrap>
                  <Typography.Text strong>{item.chapter_title || item.chapter_id}</Typography.Text>
                  <Tag color={item.unchanged ? 'default' : 'orange'}>{item.unchanged ? '未改动' : '有修订'}</Tag>
                </Space>
                {item.change_note ? (
                  <Typography.Text type="secondary">{item.change_note}</Typography.Text>
                ) : null}
                {!item.unchanged ? (
                  <Row gutter={8}>
                    <Col span={12}>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        修前摘要
                      </Typography.Text>
                      <div style={{ fontSize: 12, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                        {item.previous_plain_preview}
                      </div>
                    </Col>
                    <Col span={12}>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        修后摘要
                      </Typography.Text>
                      <div style={{ fontSize: 12, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                        {item.revised_plain_preview}
                      </div>
                    </Col>
                  </Row>
                ) : null}
              </Space>
            </List.Item>
          )}
        />
      </Modal>
    </Space>
  )
}
