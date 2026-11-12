import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Frontend runs on 5173 to avoid conflict with auth-service on 8000
  // Proxy forwards different /api paths to different microservices
  server: { 
    port: 5173,
    proxy: {
      // Most specific paths FIRST (longest prefix wins)
      "/api/v1/auth/mercadolivre": {
        target: "http://localhost:8003",
        changeOrigin: true,
        cookieDomainRewrite: { "localhost": "" },
        cookiePathRewrite: { "/": "/" },
      },
      "/api/v1/integrations": {
        target: "http://localhost:8003",
        changeOrigin: true,
        cookieDomainRewrite: { "localhost": "" },
        cookiePathRewrite: { "/": "/" },
      },
      "/api/v1/products": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
      "/api/v1/skus": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
      "/api/v1/platform-mappings": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
      "/api/v1/stores": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
      "/api/v1/orders": {
        target: "http://localhost:8004",
        changeOrigin: true,
      },
      // Auth service LAST (shortest prefix)
      "/api/v1/auth": {
        target: "http://localhost:8000",
        changeOrigin: true,
        cookieDomainRewrite: { "localhost": "" },
        cookiePathRewrite: { "/": "/" },
      },
    },
  },
  preview: { port: 5173 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});