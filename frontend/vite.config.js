import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxying /api to the backend keeps the browser on one origin during
    // development, so CORS never enters the picture while building.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        /*
         * Recharts and its d3 dependencies are most of the bundle, and only
         * three pages use them. Splitting them out means the login screen and
         * the employee list no longer pay for charts they never render, and
         * the vendor chunks stay cached across deploys of application code.
         */
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          vendor: ["axios", "lucide-react", "date-fns"],
        },
      },
    },
  },
});
