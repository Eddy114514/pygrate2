import { useMemo } from "react";
import { RangeSetBuilder, StateField } from "@codemirror/state";
import {
  Decoration,
  EditorView,
  GutterMarker,
  gutter,
} from "@codemirror/view";

function resolveWarningRange(doc, warning) {
  if (!warning || typeof warning.line !== "number" || warning.line < 1) {
    return null;
  }
  if (warning.line > doc.lines) {
    return null;
  }
  const line = doc.line(warning.line);
  const startColumn =
    typeof warning.colStart === "number" ? warning.colStart : 0;
  const endColumn =
    typeof warning.colEnd === "number" && warning.colEnd > startColumn
      ? warning.colEnd
      : Math.max(startColumn + 1, line.length);
  return {
    line,
    from: line.from + Math.min(startColumn, line.length),
    to: line.from + Math.min(endColumn, line.length),
  };
}

function buildDecorations(doc, warnings, selectedWarningId) {
  const builder = new RangeSetBuilder();
  const entries = [];
  const lineSelection = new Map();

  for (const warning of warnings) {
    const range = resolveWarningRange(doc, warning);
    if (!range) {
      continue;
    }
    const classes = [
      "rf-warning-mark",
      `rf-warning-mark--${warning.highlight || "generic"}`,
    ];
    if (warning.warningId === selectedWarningId) {
      classes.push("rf-warning-mark--selected");
      lineSelection.set(range.line.number, true);
    } else if (!lineSelection.has(range.line.number)) {
      lineSelection.set(range.line.number, false);
    }
    entries.push({
      from: range.from,
      to: Math.max(range.from + 1, range.to),
      value: Decoration.mark({ class: classes.join(" ") }),
      kind: "mark",
    });
  }

  for (const [lineNumber, isSelected] of lineSelection.entries()) {
    if (lineNumber < 1 || lineNumber > doc.lines) {
      continue;
    }
    const line = doc.line(lineNumber);
    entries.push({
      from: line.from,
      to: line.from,
      value: Decoration.line({
        class: isSelected
          ? "rf-warning-line rf-warning-line--selected"
          : "rf-warning-line",
      }),
      kind: "line",
    });
  }

  entries.sort((a, b) => {
    if (a.from !== b.from) {
      return a.from - b.from;
    }
    if (a.to !== b.to) {
      return a.to - b.to;
    }
    if (a.kind !== b.kind) {
      return a.kind === "line" ? -1 : 1;
    }
    return 0;
  });

  for (const entry of entries) {
    builder.add(entry.from, entry.to, entry.value);
  }
  return builder.finish();
}

class WarningGutterMarker extends GutterMarker {
  constructor(type, selected) {
    super();
    this.type = type;
    this.selected = selected;
  }

  toDOM() {
    const marker = document.createElement("span");
    marker.className = `rf-warning-gutter rf-warning-gutter--${this.type || "generic"}${
      this.selected ? " rf-warning-gutter--selected" : ""
    }`;
    marker.textContent = "●";
    return marker;
  }
}

function buildGutterExtension(warnings, selectedWarningId) {
  const warningsByLine = new Map();
  warnings.forEach((warning) => {
    if (typeof warning.line === "number") {
      warningsByLine.set(warning.line, warning);
    }
  });
  return gutter({
    class: "rf-warning-gutter-track",
    lineMarker(view, line) {
      const warning = warningsByLine.get(line.number);
      if (!warning) {
        return null;
      }
      return new WarningGutterMarker(
        warning.highlight || "generic",
        warning.warningId === selectedWarningId
      );
    },
  });
}

export function useWarningDecorations(warnings, selectedWarningId, onSelectWarningId) {
  return useMemo(() => {
    const decorationField = StateField.define({
      create(state) {
        return buildDecorations(state.doc, warnings, selectedWarningId);
      },
      update(_, tr) {
        return buildDecorations(tr.state.doc, warnings, selectedWarningId);
      },
      provide: (field) => EditorView.decorations.from(field),
    });

    const clickHandler = EditorView.domEventHandlers({
      mousedown(event, view) {
        const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
        if (pos == null) {
          return false;
        }
        const line = view.state.doc.lineAt(pos);
        const column = pos - line.from;
        const candidates = warnings
          .map((warning) => {
            const range = resolveWarningRange(view.state.doc, warning);
            if (!range || range.line.number !== line.number) {
              return null;
            }
            return {
              warning,
              size: range.to - range.from,
              contains: column >= range.from - line.from && column <= range.to - line.from,
            };
          })
          .filter(Boolean);
        const exact = candidates
          .filter((candidate) => candidate.contains)
          .sort((a, b) => a.size - b.size)[0];
        const match = exact || candidates[0];
        if (match && onSelectWarningId) {
          onSelectWarningId(match.warning.warningId);
        }
        return false;
      },
    });

    return [decorationField, buildGutterExtension(warnings, selectedWarningId), clickHandler];
  }, [warnings, selectedWarningId, onSelectWarningId]);
}
