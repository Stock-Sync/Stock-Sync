import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // A aplicação usa HashRouter, então pode ser servida por qualquer servidor
  // estático. A porta 8000 espelha a URL exibida nos mockups (localhost:8000/#).
  server: { port: 8000 },
  preview: { port: 8000 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    // Reaproveita o jsdom entre arquivos: cada suíte já cria seus próprios
    // providers e o custo de subir 4 ambientes não se paga aqui.
    isolate: false,
  },
});