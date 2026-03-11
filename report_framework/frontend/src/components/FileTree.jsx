import { Input, Tree, Typography } from "antd";
import { useMemo, useState } from "react";

function filterNodes(nodes, term) {
  if (!term) {
    return nodes;
  }
  return (nodes || [])
    .map((node) => {
      const title = String(node.title || "");
      if (node.children?.length) {
        const children = filterNodes(node.children, term);
        if (children.length || title.toLowerCase().includes(term)) {
          return { ...node, children };
        }
        return null;
      }
      return title.toLowerCase().includes(term) ? node : null;
    })
    .filter(Boolean);
}

export default function FileTree({ treeData, currentFile, onSelectFile }) {
  const [search, setSearch] = useState("");
  const filteredTree = useMemo(
    () => filterNodes(treeData, search.trim().toLowerCase()),
    [search, treeData]
  );

  return (
    <div className="pane">
      <div className="pane__header">
        <Typography.Title level={5} style={{ margin: 0 }}>
          Files
        </Typography.Title>
      </div>
      <Input.Search
        allowClear
        placeholder="Filter files"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <Tree
        className="file-tree"
        treeData={filteredTree}
        selectedKeys={currentFile ? [currentFile] : []}
        onSelect={(_, info) => {
          if (info.node?.isLeaf && onSelectFile) {
            onSelectFile(info.node.path);
          }
        }}
        defaultExpandAll
      />
    </div>
  );
}
