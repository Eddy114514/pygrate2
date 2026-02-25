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
    const warningsAll = data.warnings || [];
    const projectRoot = data.projectRoot || "";

    const [files, setFiles] = useState(data.files || {});
    const initialFile = data.currentFile || Object.keys(files)[0] || "";

    const [activeFile, setActiveFile] = useState(initialFile);
    const [runOutput] = useState(data.runOutput || "");

    const sourceText = files[activeFile] || "";
    const warnings = warningsAll.filter(w => w.file === activeFile);

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

            const cls = typeToHighlightClass(w.highlight);

            let fromCh = 0;
            let toCh = 0;

            const lineText = cm.getLine(lineIdx) || "";
            const orig = w.original || "";

            if (orig) {
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
                    ) : w.fixText ? (
                        <span>{w.fixText}</span>
                    ) : (
                        <span className="no-fix">(no auto-fix)</span>
                    )}
                </p>
            </Card>
        );
    };

    function findImportInsertIndex(lines) {
        let idx = 0;
        if (lines[idx] && lines[idx].startsWith("#!")) {
            idx += 1;
        }

        if (lines[idx] && /coding[:=]\s*[-\w.]+/i.test(lines[idx])) {
            idx += 1;
        }

        while (idx < lines.length && lines[idx].trim() === "") {
            idx += 1;
        }

        // Skip module docstring
        if (idx < lines.length) {
            const line = lines[idx].trim();
            if (line.startsWith('"""') || line.startsWith("'''")) {
                const quote = line.startsWith('"""') ? '"""' : "'''";
                if (line.split(quote).length - 1 >= 2) {
                    idx += 1;
                } else {
                    idx += 1;
                    while (idx < lines.length) {
                        if (lines[idx].includes(quote)) {
                            idx += 1;
                            break;
                        }
                        idx += 1;
                    }
                }
            }
        }

        while (idx < lines.length && lines[idx].trim() === "") {
            idx += 1;
        }

        return idx;
    }

    function ensureImports(text, importsToAdd) {
        if (!importsToAdd || importsToAdd.length === 0) return text;

        const lines = text.split("\n");
        const existing = new Set(
            lines
                .map((l) => l.trim())
                .filter((s) => s.startsWith("import ") || s.startsWith("from "))
        );

        const missingLines = [];
        const added = new Set();

        importsToAdd.forEach((imp) => {
            if (typeof imp !== "string") return;
            const trimmed = imp.trim();
            if (!trimmed) return;
            if (existing.has(trimmed) || added.has(trimmed)) return;
            missingLines.push(trimmed);
            added.add(trimmed);
        });

        if (!missingLines.length) return text;

        const insertAt = findImportInsertIndex(lines);
        const needBlank = insertAt < lines.length && lines[insertAt].trim() !== "";
        const toInsert = needBlank ? missingLines.concat([""]) : missingLines;
        lines.splice(insertAt, 0, ...toInsert);

        return lines.join("\n");
    }

    function collectImportsForWarnings(warningsList) {
        const set = new Set();
        warningsList.forEach((w) => {
            const arr = w.importsNeeded || w.imports || [];
            arr.forEach((imp) => {
                if (typeof imp === "string" && imp.trim()) set.add(imp.trim());
            });
        });
        return Array.from(set);
    }

    function applyFixesToText(text, warningsList) {
        let lines = text.split("\n");
        const byLine = {};
        const appliedWarnings = [];

        warningsList.forEach((w) => {
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
                if (lineStr !== lines[idx]) {
                    appliedWarnings.push(w);
                }
            });

            lines[idx] = lineStr;
        });

        if (!appliedWarnings.length) {
            return text;
        }

        const newText = lines.join("\n");
        const importsToAdd = collectImportsForWarnings(appliedWarnings);
        return ensureImports(newText, importsToAdd);
    }

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

        const currentText = cm.getValue();
        const newSource = applyFixesToText(currentText, toApply);
        cm.setValue(newSource);
        setFiles(prev => ({
            ...prev,
            [activeFile]: newSource,
        }));
    };

    const applyFixesAllFiles = async () => {
        let updatedFiles = { ...files };

        for (const file of Object.keys(updatedFiles)) {
            const fileWarnings = warningsAll.filter(
                (w) => w.file === file && typeof w.fix === "string" && w.fix.length > 0
            );
            if (!fileWarnings.length) continue;

            const originalText =
                file === activeFile && cmRef.current
                    ? cmRef.current.getValue()
                    : (updatedFiles[file] || "");

            const newText = applyFixesToText(originalText, fileWarnings);
            updatedFiles[file] = newText;
        }

        setFiles(updatedFiles);

        if (cmRef.current && activeFile && updatedFiles[activeFile] != null) {
            cmRef.current.setValue(updatedFiles[activeFile]);
        }
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
                                    const currentText = cmRef.current.getValue();

                                    const updatedFiles = {
                                        ...files,
                                        [activeFile]: currentText,
                                    };

                                    setFiles(updatedFiles);

                                    try {
                                        const resp = await fetch("/refreshprev", {
                                                method: "POST",
                                                headers: { "Content-Type": "application/json" },
                                                body: JSON.stringify({
                                                    root: projectRoot,
                                                }),
                                            });
                                        const json = await resp.json();
                                        if (!json.ok) {
                                                alert("Refresh failed for pygrate_history: " + (json.error || "unknown error"));
                                                return;
                                            }
                                        const entries = Object.entries(updatedFiles);
                                        for (let i = 0; i < entries.length; i++) {
                                            const [fname, content] = entries[i];
                                            const resp = await fetch("/save", {
                                                method: "POST",
                                                headers: { "Content-Type": "application/json" },
                                                body: JSON.stringify({
                                                    root: projectRoot,
                                                    file: fname,
                                                    sourceText: content,
                                                }),
                                            });
                                            const json = await resp.json();
                                            if (!json.ok) {
                                                alert("Save failed for " + fname + ": " + (json.error || "unknown error"));
                                                return;
                                            }
                                        }
                                        
                                    } catch (e) {
                                        alert("Save failed: " + e);
                                    }
                                }}
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
                                        setSelectedWarning(null);
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
                    </div>

                    <div className="panel panel-right">
                        <h2>Warnings</h2>

                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <h2>Warnings</h2>
                            <button
                                type="button"
                                onClick={applyFixesAllFiles}
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
