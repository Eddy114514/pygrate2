import { Space, Tag, Typography } from "antd";

export default function StatusBar({ currentFile, warningCount, dirty }) {
  return (
    <div className="status-bar">
      <Space size="middle">
        <Typography.Text type="secondary">{currentFile || "No file selected"}</Typography.Text>
        <Tag color="orange">{warningCount} warnings</Tag>
        <Tag color={dirty ? "red" : "green"}>{dirty ? "Unsaved" : "Saved"}</Tag>
      </Space>
    </div>
  );
}
