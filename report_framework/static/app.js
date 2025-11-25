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

    const data = window.PYGRATE_DATA || { sourceText: "", warnings: [], projectRoot: "", filePath: "" };
    const sourceText = data.sourceText || "";
    const warnings = data.warnings || [];
    const projectRoot = data.projectRoot || "";
    const filePath = data.filePath || "";
    const [runOutput] = useState(data.runOutput || "");


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
                let bestWarning = null;
                let bestLen = Infinity;

                for (let i = 0; i < marks.length; i++) {
                    const mark = marks[i];
                    const w = mark.__pygrateWarning;
                    if (!w) continue;

                    const range = mark.find && mark.find();
                    if (!range || !range.from || !range.to) {
                        if (bestWarning === null) {
                            bestWarning = w;
                        }
                        continue;
                    }

                    const len = range.to.ch - range.from.ch;
                    if (len < bestLen) {
                        bestLen = len;
                        bestWarning = w;
                    }
                }

                if (bestWarning) {
                    setSelectedWarning(bestWarning);
                    return;
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
                <p>
                    <button
                        type="button"
                        disabled={!w.fix}
                        onClick={() => applyFixes(w)}
                    >
                        Apply this fix
                    </button>
                </p>
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

    const applyFixes = (targetWarning = null) => {
        const cm = cmRef.current;
        if (!cm) return;

        const allWarnings = targetWarning ? [targetWarning] : warnings;
        const toApply = allWarnings.filter(
            (w) => typeof w.fix === "string" && w.fix.length > 0
        );

        if (toApply.length === 0) {
            alert("There are no auto-fixable warnings.");
            return;
        }

        let lines = cm.getValue().split("\n");
        const byLine = {};

        toApply.forEach((w) => {
            const idx = w.line - 1;
            if (idx < 0) return;
            if (!byLine[idx]) byLine[idx] = [];
            byLine[idx].push(w);
        });

        Object.keys(byLine).forEach((k) => {
            const idx = parseInt(k, 10);
            let lineStr = lines[idx] || "";
            const ws = byLine[idx];

            const sorted = ws.slice().sort((a, b) => {
                const lenA =
                    (typeof a.colStart === "number" &&
                        typeof a.colEnd === "number" &&
                        a.colEnd > a.colStart)
                        ? a.colEnd - a.colStart
                        : (a.original ? a.original.length : 0);
                const lenB =
                    (typeof b.colStart === "number" &&
                        typeof b.colEnd === "number" &&
                        b.colEnd > b.colStart)
                        ? b.colEnd - b.colStart
                        : (b.original ? b.original.length : 0);
                if (lenA !== lenB) return lenB - lenA;
                const sa = typeof a.colStart === "number" ? a.colStart : 0;
                const sb = typeof b.colStart === "number" ? b.colStart : 0;
                return sa - sb;
            });

            sorted.forEach((w) => {
                if (typeof w.fix !== "string" || !w.fix.length) return;

                const orig = w.original || "";
                if (!orig) return;

                const pos = lineStr.indexOf(orig);
                if (pos < 0) {
                    return;
                }

                const start = pos;
                const end = pos + orig.length;

                lineStr =
                    lineStr.slice(0, start) +
                    w.fix +
                    lineStr.slice(end);
            });

            lines[idx] = lineStr;
        });

        const newSource = lines.join("\n");
        cm.setValue(newSource);
    };





    return (
        <Layout style={{ height: "100%" }}>
            <Content style={{ height: "100%" }}>
                <div className="app-container">
                    <div className="panel panel-left">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <h2>Source</h2>
                            <button
                                type="button"
                                onClick={async () => {
                                    if (!cmRef.current) return;
                                    const text = cmRef.current.getValue();
                                    try {
                                        const resp = await fetch("/save", {
                                            method: "POST",
                                            headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({
                                                root: projectRoot,
                                                file: filePath,
                                                sourceText: text,
                                            }),
                                        });
                                        const json = await resp.json();
                                        if (!json.ok) {
                                            alert("Save failed: " + (json.error || "unknown error"));
                                        }
                                    } catch (e) {
                                        alert("Save failed: " + e);
                                    }
                                }}
                            >
                                Save
                            </button>
                        </div>
                        <div ref={editorHostRef} className="editor-shell" />

                        <div className="terminal">
                            <div className="terminal-header">Output</div>
                            <pre className="terminal-body">{runOutput}</pre>
                        </div>
                    </div>

                    <div className="panel panel-right">
                        <h2>Warnings</h2>

                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <h2>Warnings</h2>
                            <button
                                type="button"
                                onClick={() => applyFixes(null)}
                            >
                                Fix all
                            </button>
                        </div>

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
