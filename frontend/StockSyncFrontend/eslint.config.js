import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import prettierPlugin from "eslint-plugin-prettier";
import eslintConfigPrettier from "eslint-config-prettier";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    plugins: {
      prettier: prettierPlugin,
    },
    rules: {
      // Integração com Prettier (reporta erros de formatação no ESLint)
      "prettier/prettier": "error",

      // Regras de Qualidade e Boas Práticas
      "no-var": "error", // Proíbe o uso de 'var'
      "prefer-const": "error", // Exige 'const' para variáveis que não são reatribuídas
      "no-undef": "error", // Bloqueia variáveis não declaradas
      "no-console": ["warn", { allow: ["warn", "error"] }], // Evita console.log (permite warn/error)
      "curly": ["error", "all"], // Obriga o uso de chaves {} em blocos de controle (if, for, etc)
      "camelcase": ["error", { properties: "always" }], // Exige convenção camelCase

      // Variáveis não usadas (desativa a nativa do JS e ativa a específica do TS)
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_" },
      ],

      // Aspas: "" para strings e `` para interpolações
      "quotes": [
        "error",
        "double",
        { avoidEscape: true, allowTemplateLiterals: true },
      ],
    },
  },
  eslintConfigPrettier, // Mantido no final para desativar regras visuais conflitantes
]);