import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Layout,
  Space,
  Tree,
  Typography,
} from "antd";

const RECENTS_KEY = "pygrate-report-framework-recents";

function countLeafFiles(nodes) {
  return (nodes || []).reduce((total, node) => {
    if (node.isLeaf) {
      return total + 1;
    }
    return total + countLeafFiles(node.children || []);
  }, 0);
}

function useRecentProjects() {
  const [recents, setRecents] = useState([]);

  useEffect(() => {
    try {
      setRecents(JSON.parse(window.localStorage.getItem(RECENTS_KEY) || "[]"));
    } catch (error) {
      setRecents([]);
    }
  }, []);

  const persist = (entry) => {
    const next = [entry].concat(
      recents.filter(
        (item) =>
          item.engineRoot !== entry.engineRoot || item.projectRoot !== entry.projectRoot
      )
    ).slice(0, 5);
    setRecents(next);
    window.localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  };

  return { recents, persist };
}

export default function ProjectPage({ initialData }) {
  const [form] = Form.useForm();
  const [filterText, setFilterText] = useState("");
  const { recents, persist } = useRecentProjects();

  useEffect(() => {
    form.setFieldsValue({
      engineRoot: initialData.engineRoot || "",
      projectRoot: initialData.projectRoot || "",
    });
  }, [form, initialData.engineRoot, initialData.projectRoot]);

  const filteredTree = useMemo(() => {
    if (!filterText) {
      return initialData.treeNodes || [];
    }
    const term = filterText.toLowerCase();
    const filterNodes = (nodes) =>
      (nodes || [])
        .map((node) => {
          if (node.children) {
            const nextChildren = filterNodes(node.children);
            if (nextChildren.length || String(node.title).toLowerCase().includes(term)) {
              return { ...node, children: nextChildren };
            }
            return null;
          }
          return String(node.title).toLowerCase().includes(term) ? node : null;
        })
        .filter(Boolean);
    return filterNodes(initialData.treeNodes || []);
  }, [filterText, initialData.treeNodes]);
  const fileCount = useMemo(
    () => countLeafFiles(initialData.treeNodes || []),
    [initialData.treeNodes]
  );

  const openWorkspace = (engineRoot, projectRoot, filePath = "") => {
    persist({ engineRoot, projectRoot });
    const params = new URLSearchParams({
      engine: engineRoot,
      root: projectRoot,
    });
    if (filePath) {
      params.set("file", filePath);
    }
    window.location.href = `/?${params.toString()}`;
  };

  const onFinish = (values) => {
    openWorkspace(values.engineRoot, values.projectRoot);
  };

  return (
    <Layout className="project-page">
      <div className="project-page__hero">
        <Card className="project-page__card">
          <Space direction="vertical" size={24} style={{ width: "100%" }}>
            <div>
              <Typography.Title level={2} style={{ marginBottom: 8 }}>
                Pygrate Migration Workbench
              </Typography.Title>
              <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                Open a Python 2 project, inspect runtime warnings, preview fixes,
                and save reanalyzed results from one workspace.
              </Typography.Paragraph>
            </div>

            <Form form={form} layout="vertical" onFinish={onFinish}>
              <Form.Item label="Pygrate engine root" name="engineRoot" rules={[{ required: true }]}>
                <Input placeholder="/home/cmu/pygrate2" />
              </Form.Item>
              <Form.Item label="Project root" name="projectRoot" rules={[{ required: true }]}>
                <Input placeholder="/path/to/project" />
              </Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  Open Workspace
                </Button>
              </Space>
            </Form>

            {recents.length ? (
              <Space wrap>
                {recents.map((item) => (
                  <Button
                    key={`${item.engineRoot}::${item.projectRoot}`}
                    onClick={() => openWorkspace(item.engineRoot, item.projectRoot)}
                  >
                    {item.projectRoot}
                  </Button>
                ))}
              </Space>
            ) : null}

            <Card
              size="small"
              title={
                <Space>
                  <span>Python Files</span>
                  <Badge count={fileCount} />
                </Space>
              }
            >
              <Space direction="vertical" style={{ width: "100%" }}>
                <Input.Search
                  allowClear
                  placeholder="Filter files"
                  value={filterText}
                  onChange={(event) => setFilterText(event.target.value)}
                />
                {filteredTree.length ? (
                  <Tree
                    treeData={filteredTree}
                    defaultExpandAll
                    height={360}
                    onSelect={(_, info) => {
                      if (info.node?.isLeaf) {
                        openWorkspace(
                          initialData.engineRoot,
                          initialData.projectRoot,
                          info.node.path
                        );
                      }
                    }}
                  />
                ) : (
                  <Empty description="No Python files to show yet" />
                )}
              </Space>
            </Card>
          </Space>
        </Card>
      </div>
    </Layout>
  );
}
