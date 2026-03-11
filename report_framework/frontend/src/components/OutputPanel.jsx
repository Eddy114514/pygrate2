import { Alert, Empty, Typography } from "antd";

export default function OutputPanel({ loading, error, runOutput }) {
  if (loading) {
    return <Alert type="info" showIcon message="Analyzing…" />;
  }
  if (error) {
    return <Alert type="error" showIcon message={error} />;
  }
  if (!runOutput) {
    return <Empty description="No runtime output available" />;
  }
  return (
    <div className="terminal terminal--output">
      <Typography.Text strong>Runtime Output</Typography.Text>
      <pre>{runOutput}</pre>
    </div>
  );
}
