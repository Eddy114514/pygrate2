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
    <div className="panel-shell panel-shell--output">
      <div className="panel-shell__header">
        <Typography.Text strong>Runtime Output</Typography.Text>
      </div>
      <div className="terminal-frame">
        <div className="terminal-frame__bar">
          <span className="terminal-frame__dot terminal-frame__dot--red" />
          <span className="terminal-frame__dot terminal-frame__dot--yellow" />
          <span className="terminal-frame__dot terminal-frame__dot--green" />
          <Typography.Text className="terminal-frame__title">
            {currentFile || "terminal"}
          </Typography.Text>
        </div>
        <div className="panel-scroll panel-scroll--terminal terminal-frame__body">
          <pre className="panel-code panel-code--terminal">{runOutput}</pre>
        </div>
      </div>
    </div>
  );
}
