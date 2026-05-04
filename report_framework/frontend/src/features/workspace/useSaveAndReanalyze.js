import { useCallback } from "react";

import { loadDiff, saveAndReanalyze } from "../../api/client";

export default function useSaveAndReanalyze({
  engineRoot,
  projectRoot,
  currentFile,
  sourceText,
  messageApi,
  onSaved,
  onDiffLoaded,
}) {
  const saveCurrentFile = useCallback(async () => {
    const result = await saveAndReanalyze({
      engineRoot,
      projectRoot,
      filePath: currentFile,
      sourceText,
    });
    onSaved(result);
    messageApi.success("Saved and reanalyzed.");
    return result;
  }, [currentFile, engineRoot, messageApi, onSaved, projectRoot, sourceText]);

  const reloadSavedDiff = useCallback(async () => {
    const diff = await loadDiff({ projectRoot, filePath: currentFile });
    onDiffLoaded(diff);
    return diff;
  }, [currentFile, onDiffLoaded, projectRoot]);

  return { saveCurrentFile, reloadSavedDiff };
}
