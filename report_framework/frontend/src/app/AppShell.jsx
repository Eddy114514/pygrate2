import { Layout } from "antd";

import renderRoute from "./routes";

export default function AppShell({ bootstrap }) {
  return (
    <Layout className="app-shell">
      {renderRoute(bootstrap)}
    </Layout>
  );
}
