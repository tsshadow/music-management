import { svelteTesting } from '@testing-library/svelte/vite';
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

const devProxyTarget = process.env.VITE_DEV_API_TARGET ?? 'http://localhost:8001';

export default defineConfig({
        plugins: [tailwindcss(), sveltekit()],
  server: {
    host: true, // listen on all interfaces
    allowedHosts: ['music-importer.teunschriks.nl'],
    proxy: {
      '/api': {
        target: devProxyTarget,
        changeOrigin: true,
        secure: false,
      },
    },
    // If you proxy/HMR through a remote URL, you may also need:
    // hmr: { host: 'music-importer.teunschriks.nl', protocol: 'wss', clientPort: 443 }
  },
        test: {
                projects: [
                        {
                                extends: './vite.config.ts',
                                plugins: [svelteTesting()],
                                test: {
                                        name: 'client',
                                        environment: 'jsdom',
                                        clearMocks: true,
                                        include: ['src/**/*.svelte.{test,spec}.{js,ts}'],
                                        exclude: ['src/lib/server/**'],
                                        setupFiles: ['./vitest-setup-client.ts']
                                }
                        },
                        {
                                extends: './vite.config.ts',
                                test: {
                                        name: 'server',
                                        environment: 'node',
                                        include: ['src/**/*.{test,spec}.{js,ts}'],
                                        exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
                                }
                        }
                ]
        }
});
