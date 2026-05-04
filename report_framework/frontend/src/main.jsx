import React from "react";
import ReactDOM from "react-dom/client";
import { App as AntApp, ConfigProvider } from "antd";

import AppShell from "./app/AppShell";
import { appTheme } from "./styles/theme";
import "./styles/global.css";

const rootElement = document.getElementById("root");

if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <ConfigProvider theme={appTheme}>
        <AntApp>
          <AppShell bootstrap={window.PYGRATE_BOOTSTRAP || {}} />
        </AntApp>
      </ConfigProvider>
    </React.StrictMode>
  );
}
