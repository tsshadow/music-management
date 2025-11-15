import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  resolve: {
    alias: {
      $ui: fileURLToPath(new URL('../../../apps/web/src/lib/ui', import.meta.url)),
    },
  },
  server: {
    port: 5173,
  },
});
