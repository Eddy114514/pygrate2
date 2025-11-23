//report_framework/static/app.js
const { useEffect, useRef, useState } = React;
const { Table, Card, Typography, Empty, Layout } = antd;
const { Text } = Typography;
const { Content } = Layout;

function typeToHighlightClass(t) {
    if (t === "PRINT_WARNING") return "cm-warning-print";
    if (t === "HAS_KEY_WARNING") return "cm-warning-haskey";
    return "cm-warning-unknown";
}

function App() {
    const editorHostRef = useRef(null);
    const cmRef = useRef(null);

    const data = window.PYGRATE_DATA || { sourceText: "", warnings: [] };
    const sourceText = data.sourceText || "";
    const warnings = data.warnings || [];

    const [selectedWarning, setSelectedWarning] = useState(null);

    useEffect(() => {
        if (!editorHostRef.current) return;

        const cm = CodeMirror(editorHostRef.current, {
            value: sourceText,
            mode: "python",
            lineNumbers: true,
        });
        cmRef.current = cm;

        const warningsByLine = {};

        warnings.forEach(w => {
            const lineIdx = w.line - 1;
            if (lineIdx < 0) return;

            if (!warningsByLine[lineIdx]) warningsByLine[lineIdx] = [];
            warningsByLine[lineIdx].push(w);

            const cls = typeToHighlightClass(w.type);

            let fromCh = 0;
            let toCh = 0;

            if (
                typeof w.colStart === "number" &&
                typeof w.colEnd === "number" &&
                w.colStart >= 0 &&
                w.colEnd >= w.colStart
            ) {
                fromCh = w.colStart;
                toCh = w.colEnd;
            } else {
                const lineText = cm.getLine(lineIdx);
                fromCh = 0;
                toCh = lineText.length;
            }

            const marker = cm.markText(
                { line: lineIdx, ch: fromCh },
                { line: lineIdx, ch: toCh },
                { className: cls }
            );
            marker.__pygrateWarning = w;
        });

        function handleMouseDown(cmInstance, event) {
            const pos = cmInstance.coordsChar({
                left: event.clientX,
                top: event.clientY,
            });

            const marks = cmInstance.findMarksAt(pos);
            if (marks && marks.length > 0) {
                for (let i = 0; i < marks.length; i++) {
                    const w = marks[i].__pygrateWarning;
                    if (w) {
                        setSelectedWarning(w);
                        return;
                    }
                }
            }

            const lineIdx = pos.line;
            const list = warningsByLine[lineIdx];
            if (!list || list.length === 0) return;
            setSelectedWarning(list[0]);
        }

        cm.on("mousedown", handleMouseDown);

        return () => {
            cm.off("mousedown", handleMouseDown);
            const wrapper = cm.getWrapperElement();
            if (wrapper && wrapper.remove) wrapper.remove();
        };
    }, [sourceText, warnings]);

    const columns = [
        {
            title: "Line",
            dataIndex: "line",
            width: 70,
        },
        {
            title: "Type",
            dataIndex: "type",
            width: 150,
        },
        {
            title: "Message",
            dataIndex: "message",
            ellipsis: true,
        },
        {
            title: "Original",
            render: (_, w) => <Text code>{w.original}</Text>,
        },
        {
            title: "Suggested fix",
            render: (_, w) =>
                w.fix ? <Text code>{w.fix}</Text> : <span className="no-fix">(no auto-fix)</span>,
        },
    ];

    const renderSelectedWarning = () => {
        if (!selectedWarning) {
            return (
                <Card title="Warning details" size="small">
                    {warnings.length === 0 ? (
                        <Empty description="No warnings for this file" />
                    ) : (
                        <span>Click highlighted code to view details.</span>
                    )}
                </Card>
            );
        }

        const w = selectedWarning;
        return (
            <Card title={`Line ${w.line}`} size="small">
                <p><strong>Type:</strong> {w.type}</p>
                <p><strong>Message:</strong> {w.message}</p>
                <p>
                    <strong>Original: </strong>
                    <Text code>{w.original}</Text>
                </p>
                <p>
                    <strong>Suggested fix: </strong>
                    {w.fix ? (
                        <Text code>{w.fix}</Text>
                    ) : (
                        <span className="no-fix">(no auto-fix)</span>
                    )}
                </p>
            </Card>
        );
    };

    return (
        <Layout style={{ height: "100%" }}>
            <Content style={{ height: "100%" }}>
                <div className="app-container">
                    <div className="panel panel-left">
                        <h2>Source</h2>
                        <div ref={editorHostRef} className="editor-shell" />
                    </div>

                    <div className="panel panel-right">
                        <h2>Warnings</h2>

                        <div style={{ marginBottom: 12 }}>
                            {renderSelectedWarning()}
                        </div>

                        <div className="warnings-table-container">
                            <Table
                                className="warnings-table"
                                dataSource={warnings}
                                columns={columns}
                                rowKey={(w, i) => i}
                                size="small"
                                pagination={false}
                                onRow={record => ({
                                    onClick: () => setSelectedWarning(record),
                                })}
                            />
                        </div>
                    </div>
                </div>
            </Content>
        </Layout>
    );
}

const rootEl = document.getElementById("root");
if (rootEl) {
    const root = ReactDOM.createRoot(rootEl);
    root.render(<App />);
}
