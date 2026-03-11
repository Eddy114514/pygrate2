import { Alert, Empty, Typography } from "antd";

export default function OutputPanel({
  loading,
  error,
  runOutput,
  lastAnalyzedAt,
  warningCount,
  currentFile,
}) {
  if (loading) {
    return <Alert type="info" showIcon message="Analyzing…" />;
  }
  if (error) {
    return <Alert type="error" showIcon message={error} />;
  }
  if (!runOutput) {
    if (lastAnalyzedAt && currentFile) {
      return (
        <Alert
          type="success"
          showIcon
          message="Analysis completed"
          description={`Analyzed ${currentFile}. The program produced no stdout. Current warning count: ${warningCount ?? 0}.`}
        />
      );
    }
    return <Empty description="No runtime output available yet" />;
  }
  return (
    <div className="terminal terminal--output">
      <Typography.Text strong>Runtime Output</Typography.Text>
      <pre>{runOutput}</pre>
    </div>
  );
}
