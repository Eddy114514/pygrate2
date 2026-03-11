async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

export function openProject({ engineRoot, projectRoot }) {
  const params = new URLSearchParams({
    engine: engineRoot || "",
    root: projectRoot || "",
  });
  return requestJson(`/api/project?${params.toString()}`);
}

export function analyzeFile({ engineRoot, projectRoot, filePath }) {
  const params = new URLSearchParams({
    engine: engineRoot || "",
    root: projectRoot || "",
    file: filePath || "",
  });
  return requestJson(`/api/analyze_file?${params.toString()}`);
}

export function previewApply({ projectRoot, filePath, sourceText, warnings }) {
  return requestJson("/preview_apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      root: projectRoot,
      file: filePath,
      sourceText,
      warnings,
    }),
  });
}

export function saveAndReanalyze({ engineRoot, projectRoot, filePath, sourceText }) {
  return requestJson("/save_and_reanalyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      engine: engineRoot,
      root: projectRoot,
      file: filePath,
      sourceText,
    }),
  });
}

export function loadDiff({ projectRoot }) {
  const params = new URLSearchParams({ root: projectRoot || "" });
  return requestJson(`/api/diff?${params.toString()}`);
}

export function refreshBaseline({ projectRoot }) {
  return requestJson("/refreshprev", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ root: projectRoot }),
  });
}
