import { Table, Tag, Button, Space, Typography } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { exportUrl } from './api';

const { Text } = Typography;

function renderCell(value) {
  if (Array.isArray(value)) {
    return (
      <Space size={[0, 4]} wrap>
        {value.map((v, i) => (
          <Tag key={i}>{String(v)}</Tag>
        ))}
      </Space>
    );
  }
  if (value === null || value === undefined || value === '') {
    return <Text type="secondary">—</Text>;
  }
  return String(value);
}

export default function ResultTable({ taskId, fields, records }) {
  if (!fields || fields.length === 0) return null;

  const columns = fields.map((f) => ({
    title: f,
    dataIndex: f,
    key: f,
    render: renderCell,
    ellipsis: true,
  }));

  const dataSource = records.map((r, i) => ({ key: i, ...r }));

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between' }}>
        <Text strong>{records.length} record(s)</Text>
        {taskId && (
          <Space>
            <Button
              icon={<DownloadOutlined />}
              href={exportUrl(taskId, 'csv')}
              target="_blank"
              rel="noreferrer"
            >
              CSV
            </Button>
            <Button
              icon={<DownloadOutlined />}
              href={exportUrl(taskId, 'xlsx')}
              target="_blank"
              rel="noreferrer"
            >
              Excel
            </Button>
          </Space>
        )}
      </div>
      <Table
        columns={columns}
        dataSource={dataSource}
        size="small"
        scroll={{ x: true }}
        pagination={{ pageSize: 20, hideOnSinglePage: true }}
      />
    </div>
  );
}
