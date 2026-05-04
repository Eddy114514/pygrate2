import { Badge, Select, Space, Switch, Table, Tag, Tooltip, Typography } from "antd";

export default function WarningTable({
  warnings,
  selectedWarningId,
  typeFilter,
  autoFixOnly,
  onTypeFilterChange,
  onAutoFixOnlyChange,
  onSelectWarning,
}) {
  const typeOptions = [
    { label: "All types", value: "all" },
    ...Array.from(new Set(warnings.map((warning) => warning.type))).sort().map((type) => ({
      label: type,
      value: type,
    })),
  ];

  const columns = [
    {
      title: "Line",
      dataIndex: "line",
      width: 76,
    },
    {
      title: "Type",
      dataIndex: "type",
      width: 180,
      render: (value, warning) => (
        <Space>
          <Tag color={warning.proposal ? "green" : "default"}>{value}</Tag>
        </Space>
      ),
    },
    {
      title: "Message",
      dataIndex: "message",
      ellipsis: {
        showTitle: false,
      },
      render: (value) => (
        <Tooltip title={value}>
          <Typography.Text ellipsis>{value}</Typography.Text>
        </Tooltip>
      ),
    },
  ];

  return (
    <div className="pane pane--warnings">
      <div className="pane__header pane__header--stack">
        <Space align="center" wrap>
          <Typography.Title level={5} style={{ margin: 0 }}>
            Warnings
          </Typography.Title>
          <Badge count={warnings.length} showZero color="#fa8c16" />
        </Space>
        <Space wrap>
          <Select
            value={typeFilter}
            options={typeOptions}
            style={{ minWidth: 180 }}
            onChange={onTypeFilterChange}
          />
          <Space size="small">
            <Switch checked={autoFixOnly} onChange={onAutoFixOnlyChange} />
            <Typography.Text>Auto-fixable only</Typography.Text>
          </Space>
        </Space>
      </div>
      <div className="warning-table__container">
        <Table
          className="warning-table"
          size="small"
          rowKey={(warning) => warning.warningId}
          dataSource={warnings}
          columns={columns}
          pagination={false}
          locale={{ emptyText: "No warnings in the current view" }}
          rowClassName={(warning) =>
            warning.warningId === selectedWarningId ? "warning-table__row--selected" : ""
          }
          onRow={(record) => ({
            onClick: () => onSelectWarning(record.warningId),
          })}
        />
      </div>
    </div>
  );
}
