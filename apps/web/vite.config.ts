import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRootDir = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  plugins: [sveltekit()],
  resolve: {
    alias: {
      '@modules': resolve(projectRootDir, '../..', 'modules'),
      '@api': resolve(projectRootDir, '../..', 'api'),
    },
  },
});
