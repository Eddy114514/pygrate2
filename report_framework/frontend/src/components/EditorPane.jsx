import { useEffect, useMemo, useRef } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView } from "@codemirror/view";
import { Alert, Empty, Tabs, Tag, Typography } from "antd";

import { useWarningDecorations } from "../features/editor/useWarningDecorations";

export default function EditorPane({
  currentFile,
  openFiles,
  sourceText,
  dirty,
  warnings,
  selectedWarningId,
  onChange,
  onSelectWarningId,
  onSelectTab,
}) {
  const viewRef = useRef(null);
  const decorationExtensions = useWarningDecorations(
    warnings,
    selectedWarningId,
    onSelectWarningId
  );

  useEffect(() => {
    const warning = warnings.find((item) => item.warningId === selectedWarningId);
    const view = viewRef.current;
    if (!warning || !view || typeof warning.line !== "number") {
      return;
    }
    if (warning.line < 1 || warning.line > view.state.doc.lines) {
      return;
    }
    const docLine = view.state.doc.line(warning.line);
    view.dispatch({
      selection: { anchor: docLine.from },
      effects: EditorView.scrollIntoView(docLine.from, { y: "center" }),
    });
  }, [selectedWarningId, warnings]);

  const tabItems = useMemo(
    () =>
      openFiles.map((file) => ({
        key: file,
        label: (
          <span>
            {file}
            {file === currentFile && dirty ? <Tag color="red">dirty</Tag> : null}
          </span>
        ),
      })),
    [currentFile, dirty, openFiles]
  );

  if (!currentFile) {
    return <Empty description="Select a file to start analyzing" />;
  }

  return (
    <div className="pane pane--editor">
      <div className="pane__header">
        <Typography.Title level={5} style={{ margin: 0 }}>
          Editor
        </Typography.Title>
      </div>
      <Tabs
        size="small"
        activeKey={currentFile}
        items={tabItems}
        onChange={onSelectTab}
      />
      <div className="editor-shell">
        <CodeMirror
          key={currentFile}
          className="editor-shell__cm"
          value={sourceText}
          height="100%"
          extensions={[
            python(),
            EditorView.lineWrapping,
            ...decorationExtensions,
          ]}
          onChange={onChange}
          basicSetup={{
            lineNumbers: true,
            highlightActiveLineGutter: true,
            foldGutter: false,
          }}
          onCreateEditor={(view) => {
            viewRef.current = view;
          }}
        />
      </div>
      {dirty ? (
        <Alert
          style={{ marginTop: 8 }}
          type="warning"
          showIcon
          message="You have unsaved changes in the current file."
        />
      ) : null}
    </div>
  );
}
