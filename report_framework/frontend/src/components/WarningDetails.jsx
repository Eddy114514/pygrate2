import { Button, Card, Descriptions, Empty, Space, Tag, Typography } from "antd";

export default function WarningDetails({ warning, onApply }) {
  if (!warning) {
    return (
      <Card size="small" title="Details">
        <Empty description="Select a warning to inspect details" />
      </Card>
    );
  }

  return (
    <Card
      size="small"
      title={
        <Space>
          <span>Details</span>
          <Tag>{warning.type}</Tag>
          {warning.proposal ? <Tag color="green">Auto-fixable</Tag> : null}
          {warning.resolutionStatus ? <Tag color="blue">{warning.resolutionStatus}</Tag> : null}
        </Space>
      }
      extra={
        <Button type="primary" disabled={!warning.proposal} onClick={() => onApply([warning])}>
          Apply this fix
        </Button>
      }
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="Message">{warning.message}</Descriptions.Item>
        <Descriptions.Item label="Original">
          <Typography.Text code>{warning.original}</Typography.Text>
        </Descriptions.Item>
        <Descriptions.Item label="Suggested fix">
          {warning.fix ? (
            <Typography.Text code>{warning.fix}</Typography.Text>
          ) : (
            warning.fixText || <Typography.Text type="secondary">(no auto-fix)</Typography.Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="Required imports">
          {warning.importsNeeded?.length
            ? warning.importsNeeded.join(", ")
            : warning.imports?.length
              ? warning.imports.join(", ")
              : "None"}
        </Descriptions.Item>
        <Descriptions.Item label="Resolution">
          {warning.resolutionStatus || "n/a"}
          {warning.resolutionDetails?.statementText ? (
            <pre className="detail-pre">{warning.resolutionDetails.statementText}</pre>
          ) : null}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
