import { Alert, Empty, Typography } from "antd";

export default function DiffPanel({ title, diffText, error }) {
  if (error) {
    return <Alert type="error" showIcon message={error} />;
  }
  if (!diffText) {
    return <Empty description={`${title} is empty`} />;
  }
  return (
    <div className="terminal terminal--diff">
      <Typography.Text strong>{title}</Typography.Text>
      <pre>{diffText}</pre>
    </div>
  );
}
