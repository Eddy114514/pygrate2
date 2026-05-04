// Legacy fallback implementation kept only for migration reference.
// The supported UI path now uses report_framework/frontend + Vite bundle.

const { useEffect, useRef, useState } = React;
const { Table, Card, Typography, Empty, Layout } = antd;

const { Text } = Typography;
const { Content } = Layout;

function typeToHighlightClass(highlight) {
    const key = highlight || "unknown";
    return "cm-warning-" + key;
}

    function App() {
    const editorHostRef = useRef(null);
    const cmRef = useRef(null);

    const data = window.PYGRATE_DATA || { files: {}, warnings: [], projectRoot: "", currentFile: "" };
    const engineRoot = data.engineRoot || "";
    const projectRoot = data.projectRoot || "";

    const [files, setFiles] = useState(data.files || {});
    const [warningsAll, setWarningsAll] = useState(data.warnings || []);
    const initialFile = data.currentFile || Object.keys(files)[0] || "";

    const [activeFile, setActiveFile] = useState(initialFile);
    const [runOutput, setRunOutput] = useState(data.runOutput || "");
    const [previewDiffText, setPreviewDiffText] = useState("");

    const sourceText = files[activeFile] || "";
    const warnings = warningsAll.filter(w => w.file === activeFile);
    const [selectedWarningId, setSelectedWarningId] = useState(null);
    const selectedWarning = warnings.find((w) => w.warningId === selectedWarningId) || null;

    useEffect(() => {
        if (selectedWarningId && !warnings.some((w) => w.warningId === selectedWarningId)) {
            setSelectedWarningId(null);
        }
    }, [warnings, selectedWarningId]);

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

            const cls = typeToHighlightClass(w.highlight);

            let fromCh = 0;
            let toCh = 0;

            const lineText = cm.getLine(lineIdx) || "";
            const orig = w.original || "";

            if (
                typeof w.colStart === "number" &&
                typeof w.colEnd === "number" &&
                w.colEnd > w.colStart
            ) {
                fromCh = Math.max(0, Math.min(w.colStart, lineText.length));
                toCh = Math.max(fromCh, Math.min(w.colEnd, lineText.length));
            } else if (orig) {
                const idx = lineText.indexOf(orig);
                if (idx >= 0) {
                    fromCh = idx;
                    toCh = idx + orig.length;
                } else {
                    fromCh = 0;
                    toCh = lineText.length;
                }
            } else {
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
                    setSelectedWarningId(bestWarning.warningId);
                    return;
                }
            }

            const lineIdx = pos.line;
            const list = warningsByLine[lineIdx];
            if (!list || list.length === 0) return;
            setSelectedWarningId(list[0].warningId);
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
            render: (_, w) => {
                if (w.fix) return <Text code>{w.fix}</Text>;
                if (w.fixText) return <span>{w.fixText}</span>;
                return <span className="no-fix">(no auto-fix)</span>;
            },
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
                        disabled={!w.proposal}
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
                    ) : w.fixText ? (
                        <span>{w.fixText}</span>
                    ) : (
                        <span className="no-fix">(no auto-fix)</span>
                    )}
                </p>
            </Card>
        );
    };

    async function requestPreviewApply(targetWarnings) {
        const cm = cmRef.current;
        if (!cm) return;

        const toApply = (targetWarnings || []).filter(
            (w) => w && w.proposal
        );

        if (toApply.length === 0) {
            alert("There are no auto-fixable warnings.");
            return;
        }

        const currentText = cm.getValue();
        try {
            const resp = await fetch("/preview_apply", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    root: projectRoot,
                    file: activeFile,
                    sourceText: currentText,
                    warnings: toApply,
                }),
            });
            const json = await resp.json();
            if (!json.ok) {
                alert("Preview apply failed: " + (json.error || "unknown error"));
                return;
            }
            cm.setValue(json.sourceText || currentText);
            setFiles((prev) => ({
                ...prev,
                [activeFile]: json.sourceText || currentText,
            }));
            setPreviewDiffText(json.diffText || "");
            setSelectedWarningId(null);
            if (typeof json.appliedCount === "number" && json.appliedCount <= 0) {
                alert("No fixes were applied.");
            }
        } catch (e) {
            alert("Preview apply failed: " + e);
        }
    }

    const applyFixes = async (targetWarning = null) => {
        const allWarnings = targetWarning ? [targetWarning] : warnings;
        await requestPreviewApply(allWarnings);
    };

    const applyAllFixesInActiveFile = async () => {
        await requestPreviewApply(warnings);
    };

    async function saveAndReanalyze() {
        const cm = cmRef.current;
        if (!cm) return;

        const currentText = cm.getValue();
        try {
            const resp = await fetch("/save_and_reanalyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    engine: engineRoot,
                    root: projectRoot,
                    file: activeFile,
                    sourceText: currentText,
                }),
            });
            const json = await resp.json();
            if (!json.ok) {
                alert("Save failed: " + (json.error || "unknown error"));
                return;
            }

            const updatedText = json.sourceText || currentText;
            cm.setValue(updatedText);
            setFiles((prev) => ({
                ...prev,
                [activeFile]: updatedText,
            }));
            setWarningsAll((prev) => {
                const next = prev.filter((w) => w.file !== activeFile);
                return next.concat(json.warnings || []);
            });
            setRunOutput(json.runOutput || "");
            setPreviewDiffText("");
        } catch (e) {
            alert("Save failed: " + e);
        }
    }

    return (
        <Layout style={{ height: "100%" }}>
            <Content style={{ height: "100%" }}>
                <div className="app-container">
                    <div className="panel panel-left">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <h2>Source</h2>
                            <button
                                type="button"
                                onClick={saveAndReanalyze}
                            >
                                Save
                            </button>
                        </div>
                        <div style={{ display: "flex", gap: 8, margin: "8px 0" }}>
                            {Object.keys(files).map((f) => (
                                <button
                                    key={f}
                                    type="button"
                                    onClick={() => {
                                        if (cmRef.current && activeFile) {
                                            const text = cmRef.current.getValue();
                                            setFiles(prev => ({
                                                ...prev,
                                                [activeFile]: text,
                                            }));
                                        }
                                        setPreviewDiffText("");
                                        setSelectedWarningId(null);
                                        setActiveFile(f);
                                    }}
                                    style={{
                                        padding: "4px 8px",
                                        borderRadius: 4,
                                        border: f === activeFile ? "1px solid #1890ff" : "1px solid #ddd",
                                        background: f === activeFile ? "#e6f7ff" : "#fff",
                                        cursor: "pointer",
                                    }}
                                >
                                    {f}
                                </button>
                            ))}
                        </div>
                        <div ref={editorHostRef} className="editor-shell" />

                        <div className="terminal">
                            <div className="terminal-header">Output</div>
                            <pre className="terminal-body">{runOutput}</pre>
                        </div>
                        {previewDiffText ? (
                            <div className="terminal">
                                <div className="terminal-header">Preview diff</div>
                                <pre className="terminal-body">{previewDiffText}</pre>
                            </div>
                        ) : null}
                    </div>

                    <div className="panel panel-right">
                        <h2>Warnings</h2>

                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <h2>Warnings</h2>
                            <button
                                type="button"
                                onClick={applyAllFixesInActiveFile}
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
                                rowKey={(w) => w.warningId}
                                size="small"
                                pagination={false}
                                onRow={record => ({
                                    onClick: () => setSelectedWarningId(record.warningId),
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
