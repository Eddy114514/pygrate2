import ProjectPage from "../features/project/ProjectPage";
import WorkspacePage from "../features/workspace/WorkspacePage";

export default function renderRoute(bootstrap) {
  if ((bootstrap?.pageKind || "") === "project") {
    return <ProjectPage initialData={bootstrap} />;
  }
  return <WorkspacePage initialData={bootstrap} />;
}
