import { useCallback } from "react";

import { previewApply } from "../../api/client";

export default function usePreviewApply({
  projectRoot,
  currentFile,
  sourceText,
  onApplied,
  messageApi,
}) {
  return useCallback(
    async (targetWarnings) => {
      const selected = (targetWarnings || []).filter((warning) => warning?.proposal);
      if (!selected.length) {
        messageApi.warning("There are no auto-fixable warnings in the current selection.");
        return;
      }
      const result = await previewApply({
        projectRoot,
        filePath: currentFile,
        sourceText,
        warnings: selected,
      });
      onApplied(result);
      messageApi.success(`Preview applied ${result.appliedCount} fix${result.appliedCount === 1 ? "" : "es"}.`);
    },
    [currentFile, messageApi, onApplied, projectRoot, sourceText]
  );
}
