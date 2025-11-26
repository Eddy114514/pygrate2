const { useState, useEffect } = React;
const { Card, Layout, Input } = antd;
const { Content } = Layout;

function convertToJsTree(node, prefix = "") {
    let result = [];
    if (!node) return result;

    const files = (node["__files__"] || []).slice().sort();
    files.forEach((fname) => {
        const full = prefix ? `${prefix}/${fname}` : fname;
        result.push({
            id: full,
            parent: prefix || "#",
            text: fname,
            icon: "jstree-file",
            isLeaf: true,
            path: full,
        });
    });

    Object.keys(node)
        .filter((k) => k !== "__files__")
        .sort()
        .forEach((dirname) => {
            const child = node[dirname];
            const dirPath = prefix ? `${prefix}/${dirname}` : dirname;

            result.push({
                id: dirPath,
                parent: prefix || "#",
                text: dirname,
                icon: "jstree-folder",
                isLeaf: false,
            });

            result = result.concat(convertToJsTree(child, dirPath));
        });

    return result;
}

function ProjectApp() {
    const data = window.PYGRATE_PROJECT_DATA || {};
    const [manualPath, setManualPath] = useState("");

    const jsTreeData = React.useMemo(
        () => convertToJsTree(data.fileTree || {}, ""),
        [data.fileTree]
    );

    const goAnalyze = (file) => {
        if (!file) return;
        const params = new URLSearchParams({
            engine: data.engineRoot || "",
            root: data.projectRoot || "",
            file: file,
        });
        window.location.href = "/?" + params.toString();
    };

    useEffect(() => {
        const $ = window.jQuery || window.$;
        if (!$ || !jsTreeData) return;

        const $tree = $("#jstree");
        if (!$tree.length || !$.fn || !$.fn.jstree) return;

        try {
            $tree.jstree("destroy");
        } catch (e) {
        }

        $tree
        .jstree({
            core: {
                data: jsTreeData,
            },
        })
        .off("select_node.jstree.pygrate")
        .on("select_node.jstree.pygrate", function (e, selected) {
            const node = selected.node;
            if (node && node.original && node.original.isLeaf) {
                const file = node.original.path;
                setManualPath(file);
                goAnalyze(file);
            }
        });
        }, [jsTreeData]);

    return (
        <Layout
            style={{
                height: "100%",
                display: "flex",
                justifyContent: "center",
                alignItems: "flex-start",
                padding: 24,
            }}
        >
            <Content style={{ width: "100%", maxWidth: 720 }}>
                <div className="project-analyze-panel" style={{ marginBottom: 16 }}>
                    <h2>Analyze a file</h2>
                    <Input.Search
                        placeholder="e.g. pkg/module/foo.py"
                        enterButton="Analyze"
                        value={manualPath}
                        onChange={(e) => setManualPath(e.target.value)}
                        onSearch={(value) => goAnalyze(value)}
                        style={{ maxWidth: 600 }}
                    />
                </div>

                <Card title="Python files">
                    <div
                        id="jstree"
                        style={{
                            maxHeight: "60vh",
                            overflow: "auto",
                            background: "#fff",
                            border: "1px solid #eee",
                            borderRadius: 8,
                            padding: 8,
                        }}
                    ></div>
                </Card>
            </Content>
        </Layout>
    );
}

const projectRootEl = document.getElementById("project-root");
if (projectRootEl) {
    const projectRoot = ReactDOM.createRoot(projectRootEl);
    projectRoot.render(<ProjectApp />);
}
