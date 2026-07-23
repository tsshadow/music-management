import js from "@eslint/js";
import svelte from "eslint-plugin-svelte";
import globals from "globals";
import ts from "typescript-eslint";
import svelteParser from "svelte-eslint-parser";

export default ts.config(
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs["flat/recommended"],
  ...svelte.configs["flat/prettier"],
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
  {
    files: ["**/*.svelte"],
    languageOptions: {
      parser: svelteParser,
      parserOptions: {
        parser: ts.parser,
      },
    },
  },
  {
    rules: {
      // Svelte-specifieke regels
      "svelte/no-at-html-tags": "warn",
      "svelte/valid-compile": "error",
      "svelte/require-each-key": "error",

      // TypeScript
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],

      // Algemene kwaliteit
      "prefer-const": "error",
      "no-var": "error",
      "no-inline-comments": "off",
      "no-useless-assignment": "warn",
    },
  },
  {
    ignores: ["build/", ".svelte-kit/", "dist/", "node_modules/"],
  },
);
