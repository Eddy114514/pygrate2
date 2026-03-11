import {
  Badge,
  Button,
  Input,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  PlayCircleOutlined,
  SaveOutlined,
  ThunderboltOutlined,
  FileSearchOutlined,
  ReloadOutlined,
} from "@ant-design/icons";

export default function Toolbar({
  engineRoot,
  projectRoot,
  currentFile,
  warningCount,
  autoFixableCount,
  dirty,
  lastAnalyzedAt,
  loading,
  onAnalyze,
  onSave,
  onPreviewSelected,
  onFixSelected,
  onFixAll,
  onLoadDiff,
}) {
  return (
    <div className="workspace-toolbar">
      <div className="workspace-toolbar__meta">
        <Typography.Text strong>{currentFile || "No file selected"}</Typography.Text>
        <Tooltip title={engineRoot}>
          <Tag>{engineRoot || "No engine root"}</Tag>
        </Tooltip>
        <Tooltip title={projectRoot}>
          <Tag color="blue">{projectRoot || "No project root"}</Tag>
        </Tooltip>
      </div>

      <Space wrap>
        <Button icon={<PlayCircleOutlined />} onClick={onAnalyze} loading={loading}>
          Analyze
        </Button>
        <Button icon={<SaveOutlined />} type="primary" onClick={onSave} loading={loading}>
          Save
        </Button>
        <Button icon={<ThunderboltOutlined />} onClick={onPreviewSelected}>
          Preview Apply
        </Button>
        <Button onClick={onFixSelected}>Fix Selected</Button>
        <Button onClick={onFixAll}>Fix All</Button>
        <Button icon={<ReloadOutlined />} onClick={onAnalyze}>
          Reanalyze
        </Button>
        <Button icon={<FileSearchOutlined />} onClick={onLoadDiff}>
          View Diff
        </Button>
      </Space>

      <div className="workspace-toolbar__status">
        <Badge count={warningCount} showZero color="#fa8c16" />
        <Tag color={autoFixableCount ? "green" : "default"}>
          Auto-fixable {autoFixableCount}
        </Tag>
        <Tag color={dirty ? "red" : "default"}>{dirty ? "Unsaved" : "Saved"}</Tag>
        {lastAnalyzedAt ? (
          <Typography.Text type="secondary">
            Last analyzed {new Date(lastAnalyzedAt).toLocaleTimeString()}
          </Typography.Text>
        ) : null}
      </div>
    </div>
  );
}
