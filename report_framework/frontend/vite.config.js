import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
  build: {
    manifest: true,
    outDir: path.resolve(__dirname, "../static/frontend"),
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, "src/main.jsx"),
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return null;
          }
          if (id.includes("antd") || id.includes("@ant-design")) {
            return "antd-vendor";
          }
          if (id.includes("@codemirror") || id.includes("@uiw/react-codemirror")) {
            return "editor-vendor";
          }
          if (id.includes("react")) {
            return "react-vendor";
          }
          return undefined;
        },
      },
    },
  },
});
