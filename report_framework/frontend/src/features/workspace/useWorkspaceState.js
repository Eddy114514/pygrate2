import { useEffect, useMemo, useState } from "react";

import { analyzeFile } from "../../api/client";

export default function useWorkspaceState(initialData) {
  const [projectState, setProjectState] = useState({
    engineRoot: initialData.engineRoot || "",
    projectRoot: initialData.projectRoot || "",
    treeNodes: initialData.treeNodes || [],
    currentFile: initialData.currentFile || "",
    openFiles: initialData.currentFile ? [initialData.currentFile] : [],
  });
  const [editorState, setEditorState] = useState({
    sourceText: initialData.sourceText || "",
    savedSourceText: initialData.sourceText || "",
  });
  const [warningState, setWarningState] = useState({
    warnings: initialData.warnings || [],
    selectedWarningId: null,
    typeFilter: "all",
    autoFixOnly: false,
  });
  const [analysisState, setAnalysisState] = useState({
    runOutput: initialData.runOutput || "",
    loading: false,
    error: null,
    lastAnalyzedAt: initialData.currentFile ? new Date().toISOString() : null,
  });
  const [diffState, setDiffState] = useState({
    previewDiffText: initialData.previewDiffText || "",
    savedDiffText: "",
    loading: false,
    error: null,
    activeTab: "output",
  });

  const dirty = editorState.sourceText !== editorState.savedSourceText;

  useEffect(() => {
    if (
      warningState.selectedWarningId &&
      !warningState.warnings.some(
        (warning) => warning.warningId === warningState.selectedWarningId
      )
    ) {
      setWarningState((prev) => ({ ...prev, selectedWarningId: null }));
    }
  }, [warningState.selectedWarningId, warningState.warnings]);

  const filteredWarnings = useMemo(() => {
    return warningState.warnings.filter((warning) => {
      if (
        warningState.typeFilter !== "all" &&
        warning.type !== warningState.typeFilter
      ) {
        return false;
      }
      if (warningState.autoFixOnly && !warning.proposal) {
        return false;
      }
      return true;
    });
  }, [warningState.autoFixOnly, warningState.typeFilter, warningState.warnings]);

  const selectedWarning = useMemo(
    () =>
      warningState.warnings.find(
        (warning) => warning.warningId === warningState.selectedWarningId
      ) || null,
    [warningState.selectedWarningId, warningState.warnings]
  );

  const analyzeCurrentFile = async (filePath = projectState.currentFile) => {
    if (!filePath) {
      return null;
    }
    setAnalysisState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const result = await analyzeFile({
        engineRoot: projectState.engineRoot,
        projectRoot: projectState.projectRoot,
        filePath,
      });
      setProjectState((prev) => ({
        ...prev,
        currentFile: filePath,
        openFiles: prev.openFiles.includes(filePath)
          ? prev.openFiles
          : prev.openFiles.concat(filePath),
      }));
      setEditorState({
        sourceText: result.sourceText || "",
        savedSourceText: result.sourceText || "",
      });
      setWarningState((prev) => ({
        ...prev,
        warnings: result.warnings || [],
      }));
      setAnalysisState({
        runOutput: result.runOutput || "",
        loading: false,
        error: null,
        lastAnalyzedAt: new Date().toISOString(),
      });
      return result;
    } catch (error) {
      setAnalysisState((prev) => ({
        ...prev,
        loading: false,
        error: error.message,
      }));
      throw error;
    }
  };

  return {
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
  };
}
