import { useMemo } from "react";
import {
  Alert,
  App,
  Card,
  Empty,
  Layout,
  Segmented,
  Space,
  Splitter,
  Tabs,
} from "antd";

import Toolbar from "../../components/Toolbar";
import FileTree from "../../components/FileTree";
import EditorPane from "../../components/EditorPane";
import WarningDetails from "../../components/WarningDetails";
import WarningTable from "../../components/WarningTable";
import OutputPanel from "../../components/OutputPanel";
import DiffPanel from "../../components/DiffPanel";
import StatusBar from "../../components/StatusBar";
import usePreviewApply from "./usePreviewApply";
import useSaveAndReanalyze from "./useSaveAndReanalyze";
import useWorkspaceState from "./useWorkspaceState";

export default function WorkspacePage({ initialData }) {
  const { message } = App.useApp();
  const state = useWorkspaceState(initialData);
  const {
    projectState,
    setProjectState,
    editorState,
    setEditorState,
    warningState,
    setWarningState,
    analysisState,
    setAnalysisState,
    diffState,
    setDiffState,
    dirty,
    filteredWarnings,
    selectedWarning,
    analyzeCurrentFile,
  } = state;

  const autoFixableCount = useMemo(
    () => warningState.warnings.filter((warning) => warning.proposal).length,
    [warningState.warnings]
  );

  const applyPreview = usePreviewApply({
    projectRoot: projectState.projectRoot,
    currentFile: projectState.currentFile,
    sourceText: editorState.sourceText,
    messageApi: message,
    onApplied: (result) => {
      setEditorState((prev) => ({
        ...prev,
        sourceText: result.sourceText || prev.sourceText,
      }));
      setDiffState((prev) => ({
        ...prev,
        previewDiffText: result.diffText || "",
        activeTab: "preview",
      }));
      setWarningState((prev) => ({ ...prev, selectedWarningId: null }));
    },
  });

  const { saveCurrentFile, reloadSavedDiff } = useSaveAndReanalyze({
    engineRoot: projectState.engineRoot,
    projectRoot: projectState.projectRoot,
    currentFile: projectState.currentFile,
    sourceText: editorState.sourceText,
    messageApi: message,
    onSaved: (result) => {
      setEditorState({
        sourceText: result.sourceText || editorState.sourceText,
        savedSourceText: result.sourceText || editorState.sourceText,
      });
      setWarningState((prev) => ({
        ...prev,
        warnings: result.warnings || [],
      }));
      setAnalysisState((prev) => ({
        ...prev,
        runOutput: result.runOutput || "",
        lastAnalyzedAt: new Date().toISOString(),
        error: null,
      }));
      setDiffState((prev) => ({
        ...prev,
        previewDiffText: "",
        activeTab: "output",
      }));
    },
    onDiffLoaded: (diff) => {
      setDiffState((prev) => ({
        ...prev,
        savedDiffText: diff.diff_text || "",
        activeTab: "saved",
        error: null,
      }));
    },
  });

  const selectFile = async (filePath) => {
    try {
      await analyzeCurrentFile(filePath);
      setDiffState((prev) => ({
        ...prev,
        previewDiffText: "",
        activeTab: "output",
      }));
    } catch (error) {
      message.error(error.message);
    }
  };

  const runAnalyze = async () => {
    try {
      await analyzeCurrentFile(projectState.currentFile);
      setDiffState((prev) => ({ ...prev, activeTab: "output" }));
      message.success("Analysis completed.");
    } catch (error) {
      message.error(error.message);
    }
  };

  const loadSavedDiff = async () => {
    try {
      await reloadSavedDiff();
    } catch (error) {
      setDiffState((prev) => ({ ...prev, error: error.message }));
      message.error(error.message);
    }
  };

  const openDiffPage = () => {
    if (!projectState.projectRoot) {
      message.warning("No project root is loaded.");
      return;
    }
    const params = new URLSearchParams({
      root: projectState.projectRoot || "",
    });
    if (projectState.currentFile) {
      params.set("file", projectState.currentFile);
    }
    window.open(`/diff?${params.toString()}`, "_blank", "noopener,noreferrer");
  };

  const handleBottomTabChange = async (key) => {
    setDiffState((prev) => ({ ...prev, activeTab: key }));
    if (key === "saved") {
      await loadSavedDiff();
    }
  };

  const warningTabs = [
    {
      key: "output",
      label: "Output",
      children: (
        <OutputPanel
          loading={analysisState.loading}
          error={analysisState.error}
          runOutput={analysisState.runOutput}
          lastAnalyzedAt={analysisState.lastAnalyzedAt}
          warningCount={warningState.warnings.length}
          currentFile={projectState.currentFile}
        />
      ),
    },
    {
      key: "preview",
      label: "Preview Diff",
      children: (
        <DiffPanel
          title="Preview Diff"
          diffText={diffState.previewDiffText}
          error={diffState.error}
        />
      ),
    },
    {
      key: "saved",
      label: "Saved Diff",
      children: (
        <DiffPanel
          title="Saved Diff"
          diffText={diffState.savedDiffText}
          error={diffState.error}
        />
      ),
    },
  ];

  return (
    <Layout className="workspace-page">
      <Toolbar
        engineRoot={projectState.engineRoot}
        projectRoot={projectState.projectRoot}
        currentFile={projectState.currentFile}
        warningCount={warningState.warnings.length}
        autoFixableCount={autoFixableCount}
        dirty={dirty}
        lastAnalyzedAt={analysisState.lastAnalyzedAt}
        loading={analysisState.loading}
        onAnalyze={runAnalyze}
        onSave={saveCurrentFile}
        onPreviewSelected={() => applyPreview(selectedWarning ? [selectedWarning] : filteredWarnings)}
        onFixSelected={() => applyPreview(selectedWarning ? [selectedWarning] : [])}
        onFixAll={() => applyPreview(filteredWarnings)}
        onOpenDiffPage={openDiffPage}
      />

      {analysisState.error ? (
        <Alert
          style={{ margin: "0 16px 16px" }}
          type="error"
          showIcon
          message={analysisState.error}
        />
      ) : null}

      <Layout.Content className="workspace-content">
        <Splitter className="workspace-splitter">
          <Splitter.Panel defaultSize="22%" min="18%" max="32%">
            <FileTree
              treeData={projectState.treeNodes}
              currentFile={projectState.currentFile}
              onSelectFile={selectFile}
            />
          </Splitter.Panel>
          <Splitter.Panel defaultSize="48%" min="36%">
            <div className="workspace-center">
              <EditorPane
                currentFile={projectState.currentFile}
                openFiles={projectState.openFiles}
                sourceText={editorState.sourceText}
                dirty={dirty}
                warnings={warningState.warnings}
                selectedWarningId={warningState.selectedWarningId}
                onChange={(value) =>
                  setEditorState((prev) => ({
                    ...prev,
                    sourceText: value,
                  }))
                }
                onSelectWarningId={(warningId) =>
                  setWarningState((prev) => ({ ...prev, selectedWarningId: warningId }))
                }
                onSelectTab={selectFile}
              />
              <Card className="workspace-bottom-card" size="small">
                <Tabs
                  className="workspace-bottom-tabs"
                  activeKey={diffState.activeTab}
                  items={warningTabs}
                  onChange={handleBottomTabChange}
                />
              </Card>
            </div>
          </Splitter.Panel>
          <Splitter.Panel defaultSize="30%" min="24%">
            <div className="workspace-right">
              <Card className="workspace-summary-card" size="small">
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Segmented
                    value={warningState.typeFilter}
                    options={[
                      { label: "All", value: "all" },
                      { label: "Auto-fix", value: warningState.autoFixOnly ? "auto" : "all" },
                    ]}
                    onChange={(value) => {
                      if (value === "auto") {
                        setWarningState((prev) => ({
                          ...prev,
                          autoFixOnly: true,
                          typeFilter: "all",
                        }));
                      } else {
                        setWarningState((prev) => ({
                          ...prev,
                          autoFixOnly: false,
                          typeFilter: "all",
                        }));
                      }
                    }}
                  />
                  <StatusBar
                    currentFile={projectState.currentFile}
                    warningCount={warningState.warnings.length}
                    dirty={dirty}
                  />
                </Space>
              </Card>
              <WarningTable
                warnings={filteredWarnings}
                selectedWarningId={warningState.selectedWarningId}
                typeFilter={warningState.typeFilter}
                autoFixOnly={warningState.autoFixOnly}
                onTypeFilterChange={(value) =>
                  setWarningState((prev) => ({ ...prev, typeFilter: value }))
                }
                onAutoFixOnlyChange={(value) =>
                  setWarningState((prev) => ({ ...prev, autoFixOnly: value }))
                }
                onSelectWarning={(warningId) =>
                  setWarningState((prev) => ({ ...prev, selectedWarningId: warningId }))
                }
              />
              <WarningDetails warning={selectedWarning} onApply={applyPreview} />
            </div>
          </Splitter.Panel>
        </Splitter>
      </Layout.Content>
    </Layout>
  );
}
