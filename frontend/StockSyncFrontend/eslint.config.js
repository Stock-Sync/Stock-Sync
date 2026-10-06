import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
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
    rules: {
      // Regras de Lógica e Qualidade
      "no-var": "error",
      "prefer-const": "error",
      "no-undef": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "curly": ["error", "all"],
      "camelcase": ["error", { properties: "always" }],

      // Evita o erro de escrever "${var}" dentro de strings normais com aspas
      "no-template-curly-in-string": "error",

      // Força o uso de template literals APENAS quando houver interpolação/variáveis
      "quotes": [
        "error",
        "double",
        { avoidEscape: true, allowTemplateLiterals: false }
      ],

      // Gerenciamento de variáveis não utilizadas
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_" },
      ],
    },
  },
  {
    /**
     * Os tipos e o mock espelham os schemas do backend (snake_case), e
     * renomear os campos quebraria a troca do mock pelo client HTTP real.
     * A regra `camelcase` fica desligada apenas nesses arquivos.
     */
    files: [
      "src/types/**/*.ts",
      "src/mock/**/*.ts",
      "src/lib/api/**/*.ts",
      "src/features/**/*.test.tsx",
      // Queries e formulários constroem payloads com os nomes dos schemas.
      "src/features/**/queries.ts",
      "src/features/stores/StoreFormPage.tsx",
    ],
    rules: {
      camelcase: "off",
    },
  },
]);