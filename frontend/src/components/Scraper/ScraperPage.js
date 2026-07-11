import { useState, useEffect, useCallback } from 'react';
import {
  Input, Button, Card, Space, Typography, Timeline, Tag, Alert, Table, message, Divider,
} from 'antd';
import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { runScrapeStream, fetchTasks, fetchTaskDetail } from './api';
import ResultTable from './ResultTable';
import './scraper.css';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

const STATUS_COLORS = {
  completed: 'success',
  failed: 'error',
  fetching: 'processing',
  parsing: 'processing',
  planning: 'processing',
  extracting: 'processing',
  validating: 'processing',
};

export default function ScraperPage() {
  const [url, setUrl] = useState('https://quotes.toscrape.com/');
  const [prompt, setPrompt] = useState("extract each quote's author and its tags");
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [tasks, setTasks] = useState([]);

  const loadTasks = useCallback(async () => {
    try {
      const data = await fetchTasks(20, 0);
      setTasks(data.items);
    } catch (e) {
      // history is non-critical
    }
  }, []);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const run = async () => {
    if (!url.trim()) return;
    setRunning(true);
    setProgress([]);
    setResult(null);
    setError(null);
    try {
      await runScrapeStream(
        { url, prompt: prompt.trim() || null },
        {
          onProgress: (entry) =>
            setProgress((prev) => [...prev, entry]),
          onCompleted: (resp) => {
            setResult(resp);
            if (resp.status === 'failed' && resp.error) setError(resp.error);
          },
          onError: (err) => setError(err),
        }
      );
    } catch (e) {
      setError({ code: 'CLIENT_ERROR', message: e.message });
    } finally {
      setRunning(false);
      loadTasks();
    }
  };

  const openTask = async (taskId) => {
    try {
      const detail = await fetchTaskDetail(taskId);
      setProgress(detail.execution_log || []);
      setResult({
        task_id: detail.id,
        status: detail.status,
        url: detail.url,
        fetch_method: detail.fetch_method,
        data: {
          fields: detail.fields,
          records: detail.records,
          strategy: detail.strategy,
          row_count: detail.row_count,
          field_coverage: detail.field_coverage,
        },
        validation: detail.validation,
        error: detail.error_code
          ? { code: detail.error_code, message: detail.error_message }
          : null,
      });
      setError(detail.error_code ? { code: detail.error_code, message: detail.error_message } : null);
    } catch (e) {
      message.error('Failed to load task');
    }
  };

  const data = result?.data || {};
  const isStructureOnly = data.structured_dom !== undefined;

  const historyColumns = [
    { title: 'When', dataIndex: 'created_at', key: 'created_at',
      render: (t) => new Date(t).toLocaleString(), width: 170 },
    { title: 'URL', dataIndex: 'url', key: 'url', ellipsis: true },
    { title: 'Prompt', dataIndex: 'prompt', key: 'prompt', ellipsis: true,
      render: (p) => p || <Text type="secondary">—</Text> },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 110,
      render: (s) => <Tag color={STATUS_COLORS[s]}>{s}</Tag> },
    { title: 'Rows', dataIndex: 'row_count', key: 'row_count', width: 70 },
    { title: 'Strategy', dataIndex: 'strategy', key: 'strategy', width: 100,
      render: (s) => (s ? <Tag>{s}</Tag> : null) },
  ];

  return (
    <div className="scraper-page">
      <Title level={3}>Webpage Content Scraper Agent</Title>
      <Paragraph type="secondary">
        Give a URL and describe what to extract. The agent plans fields, picks a
        strategy (CSS selectors or direct LLM extraction), self-checks the result, and
        returns a structured table.
      </Paragraph>

      <Card size="small" className="input-card">
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Input
            addonBefore="URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://..."
          />
          <TextArea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="What to extract, in plain language (leave empty to only inspect page structure)"
            autoSize={{ minRows: 2, maxRows: 5 }}
          />
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={run}
            loading={running}
            disabled={!url.trim()}
          >
            Run
          </Button>
        </Space>
      </Card>

      <div className="results-grid">
        {(progress.length > 0 || running) && (
          <Card size="small" title="Execution timeline" className="timeline-card">
            <Timeline
              items={progress.map((e) => ({
                color: e.message?.startsWith('failed') ? 'red'
                  : e.step === 'validate_result' ? 'green' : 'blue',
                children: (
                  <div>
                    <Text strong>{e.step}</Text>
                    <br />
                    <Text type="secondary">{e.message}</Text>
                  </div>
                ),
              }))}
              pending={running ? 'Working…' : false}
            />
          </Card>
        )}

        <div className="result-main">
          {error && (
            <Alert
              type="error"
              showIcon
              message={error.code}
              description={error.message}
              style={{ marginBottom: 16 }}
            />
          )}

          {result && !isStructureOnly && data.fields && (
            <Card
              size="small"
              title={
                <Space>
                  <span>Results</span>
                  {data.strategy && <Tag color="blue">{data.strategy} strategy</Tag>}
                  {result.validation && (
                    <Tag color={result.validation.ok ? 'success' : 'warning'}>
                      {result.validation.ok ? 'validated' : 'best-effort'}
                    </Tag>
                  )}
                </Space>
              }
            >
              <ResultTable
                taskId={result.task_id}
                fields={data.fields}
                records={data.records || []}
              />
            </Card>
          )}

          {result && isStructureOnly && (
            <Alert
              type="info"
              showIcon
              message="Structure-only mode"
              description="No prompt was given, so the page structure was inspected but nothing was extracted."
            />
          )}
        </div>
      </div>

      <Divider />

      <Card
        size="small"
        title="History"
        extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadTasks}>Refresh</Button>}
      >
        <Table
          columns={historyColumns}
          dataSource={tasks.map((t) => ({ key: t.id, ...t }))}
          size="small"
          onRow={(record) => ({ onClick: () => openTask(record.id), style: { cursor: 'pointer' } })}
          pagination={{ pageSize: 8, hideOnSinglePage: true }}
        />
      </Card>
    </div>
  );
}
