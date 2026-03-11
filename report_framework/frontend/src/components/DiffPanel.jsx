import { Alert, Empty, Tag, Typography } from "antd";

function parseHunkHeader(header) {
  const match = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(header);
  if (!match) {
    return null;
  }
  return {
    oldStart: Number(match[1]),
    newStart: Number(match[3]),
  };
}

function normalizePath(path) {
  if (!path) {
    return null;
  }
  return path.replace(/^[ab]\//, "");
}

function getFileStatus(file) {
  if (file.oldPath === "/dev/null") {
    return "added";
  }
  if (file.newPath === "/dev/null") {
    return "deleted";
  }
  if (normalizePath(file.oldPath) && normalizePath(file.newPath) && normalizePath(file.oldPath) !== normalizePath(file.newPath)) {
    return "renamed";
  }
  return "modified";
}

function getDisplayPath(file) {
  const oldPath = normalizePath(file.oldPath);
  const newPath = normalizePath(file.newPath);
  if (oldPath && newPath && oldPath !== newPath) {
    return `${oldPath} -> ${newPath}`;
  }
  return newPath || oldPath || file.diffPath || "Untitled diff";
}

function parseUnifiedDiff(diffText) {
  const lines = diffText.replace(/\r\n/g, "\n").split("\n");
  const files = [];
  let currentFile = null;
  let currentHunk = null;
  let lineState = null;

  const flushHunk = () => {
    if (currentFile && currentHunk) {
      currentFile.hunks.push(currentHunk);
    }
    currentHunk = null;
    lineState = null;
  };

  const flushFile = () => {
    flushHunk();
    if (currentFile) {
      currentFile.displayPath = getDisplayPath(currentFile);
      currentFile.status = getFileStatus(currentFile);
      currentFile.additions = currentFile.hunks.reduce(
        (count, hunk) => count + hunk.lines.filter((line) => line.type === "addition").length,
        0
      );
      currentFile.deletions = currentFile.hunks.reduce(
        (count, hunk) => count + hunk.lines.filter((line) => line.type === "deletion").length,
        0
      );
      files.push(currentFile);
    }
    currentFile = null;
  };

  const ensureFile = () => {
    if (!currentFile) {
      currentFile = {
        diffPath: null,
        oldPath: null,
        newPath: null,
        hunks: [],
      };
    }
    return currentFile;
  };

  for (const line of lines) {
    if (line.startsWith("diff --git ")) {
      flushFile();
      const parts = line.split(" ");
      currentFile = {
        diffPath: parts.slice(2).join(" "),
        oldPath: null,
        newPath: null,
        hunks: [],
      };
      continue;
    }

    const file = ensureFile();

    if (line.startsWith("--- ")) {
      flushHunk();
      file.oldPath = line.slice(4).trim();
      continue;
    }

    if (line.startsWith("+++ ")) {
      file.newPath = line.slice(4).trim();
      continue;
    }

    if (line.startsWith("@@ ")) {
      flushHunk();
      currentHunk = {
        header: line,
        lines: [],
      };
      const parsed = parseHunkHeader(line);
      lineState = parsed
        ? { oldNumber: parsed.oldStart, newNumber: parsed.newStart }
        : null;
      continue;
    }

    if (!currentHunk) {
      continue;
    }

    if (line.startsWith("\\")) {
      currentHunk.lines.push({
        type: "meta",
        oldNumber: null,
        newNumber: null,
        prefix: "",
        text: line,
      });
      continue;
    }

    const prefix = line[0] || " ";
    const text = line.slice(1);
    const row = {
      type: "context",
      oldNumber: null,
      newNumber: null,
      prefix,
      text,
    };

    if (prefix === "+") {
      row.type = "addition";
      row.newNumber = lineState ? lineState.newNumber++ : null;
    } else if (prefix === "-") {
      row.type = "deletion";
      row.oldNumber = lineState ? lineState.oldNumber++ : null;
    } else {
      row.oldNumber = lineState ? lineState.oldNumber++ : null;
      row.newNumber = lineState ? lineState.newNumber++ : null;
    }

    currentHunk.lines.push(row);
  }

  flushFile();
  return files.filter((file) => file.hunks.length > 0);
}

function statusColor(status) {
  switch (status) {
    case "added":
      return "green";
    case "deleted":
      return "red";
    case "renamed":
      return "gold";
    default:
      return "blue";
  }
}

export default function DiffPanel({ title, diffText, error }) {
  if (error) {
    return <Alert type="error" showIcon message={error} />;
  }
  if (!diffText) {
    return <Empty description={`${title} is empty`} />;
  }

  const files = parseUnifiedDiff(diffText);

  if (!files.length) {
    return (
      <div className="panel-shell panel-shell--diff">
        <div className="panel-shell__header">
          <Typography.Text strong>{title}</Typography.Text>
        </div>
        <div className="panel-scroll panel-scroll--terminal">
          <pre className="panel-code">{diffText}</pre>
        </div>
      </div>
    );
  }

  return (
    <div className="panel-shell panel-shell--diff">
      <div className="panel-shell__header panel-shell__header--spread">
        <Typography.Text strong>{title}</Typography.Text>
        <Typography.Text type="secondary">{files.length} file diff{files.length === 1 ? "" : "s"}</Typography.Text>
      </div>
      <div className="panel-scroll panel-scroll--diff">
        <div className="gh-diff">
          {files.map((file) => (
            <section
              key={`${file.displayPath}-${file.hunks.length}`}
              className="gh-diff-file"
            >
              <header className="gh-diff-file__header">
                <div className="gh-diff-file__title">
                  <Tag color={statusColor(file.status)}>{file.status}</Tag>
                  <Typography.Text strong>{file.displayPath}</Typography.Text>
                </div>
                <div className="gh-diff-file__stats">
                  <span className="gh-diff-file__count gh-diff-file__count--add">+{file.additions}</span>
                  <span className="gh-diff-file__count gh-diff-file__count--del">-{file.deletions}</span>
                </div>
              </header>
              <div className="gh-diff-file__body">
                {file.hunks.map((hunk) => (
                  <div key={`${file.displayPath}-${hunk.header}`} className="gh-diff-hunk">
                    <div className="gh-diff-hunk__header">{hunk.header}</div>
                    <div className="gh-diff-hunk__rows">
                      {hunk.lines.map((line, index) => (
                        <div
                          key={`${hunk.header}-${index}`}
                          className={`gh-diff-row gh-diff-row--${line.type}`}
                        >
                          <span className="gh-diff-row__number">
                            {line.oldNumber ?? ""}
                          </span>
                          <span className="gh-diff-row__number">
                            {line.newNumber ?? ""}
                          </span>
                          <code className="gh-diff-row__content">
                            {line.type === "meta" ? line.text : `${line.prefix}${line.text}`}
                          </code>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
