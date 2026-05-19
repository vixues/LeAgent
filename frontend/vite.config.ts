import { defineConfig, mergeConfig, type Plugin } from 'vite';
import { defineConfig as defineVitestConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';

function obfuscateRouteChunksPlugin(): Plugin {
  return {
    name: 'leagent-obfuscate-route-chunks',
    apply: 'build',
    async closeBundle() {
      if (process.env.VITE_SKIP_OBFUSCATION === '1') return;
      const assetsDir = path.resolve(__dirname, 'dist', 'assets');
      if (!fs.existsSync(assetsDir)) return;
      const { default: JavaScriptObfuscator } = await import('javascript-obfuscator');
      const targets = /ChatView|FlowPage|WorkflowList/i;
      for (const file of fs.readdirSync(assetsDir)) {
        if (!file.endsWith('.js') || !targets.test(file)) continue;
        const full = path.join(assetsDir, file);
        const src = fs.readFileSync(full, 'utf8');
        const ob = JavaScriptObfuscator.obfuscate(src, {
          compact: true,
          controlFlowFlattening: false,
          deadCodeInjection: false,
          identifierNamesGenerator: 'hexadecimal',
          numbersToExpressions: false,
          simplify: true,
          stringArray: true,
          stringArrayThreshold: 0.75,
          transformObjectKeys: true,
        });
        fs.writeFileSync(full, ob.getObfuscatedCode(), 'utf8');
      }
    },
  };
}

export default defineConfig(({ mode }) => {
  const isProd = mode === 'production';
  const isDesktop = process.env.VITE_DESKTOP === 'true';

  return mergeConfig(
    {
      base: isDesktop ? './' : '/',
      plugins: [react(), ...(isProd ? [obfuscateRouteChunksPlugin()] : [])],
      resolve: {
        alias: {
          '@': path.resolve(__dirname, './src'),
        },
      },
      server: {
        port: 5173,
        host: true,
        proxy: {
          '/api': {
            target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:7860',
            changeOrigin: true,
            /** Forward WS upgrades (e.g. ``/api/v1/notifications/ws``); HTTP-only proxy drops them. */
            ws: true,
          },
          '/ws': {
            target: process.env.VITE_WS_PROXY_TARGET || 'ws://localhost:7860',
            ws: true,
          },
        },
      },
      build: {
        outDir: 'dist',
        target: isDesktop ? 'chrome120' : undefined,
        sourcemap: !isProd,
        modulePreload: isDesktop ? { polyfill: false } : undefined,
        minify: isProd ? 'terser' : undefined,
        terserOptions: isProd
          ? {
              format: { comments: false },
              compress: {
                drop_console: true,
                drop_debugger: true,
                passes: 2,
              },
              mangle: { safari10: true },
            }
          : undefined,
        rollupOptions: {
          output: {
            manualChunks(id: string) {
              if (!id.includes('node_modules')) return undefined;
              if (id.includes('/@xyflow/')) return 'flow';
              if (id.includes('/react-router') || id.includes('/@remix-run/router'))
                return 'router';
              if (id.includes('/@tanstack/')) return 'query';
              if (id.includes('/i18next') || id.includes('/react-i18next'))
                return 'i18n';
              if (
                id.includes('/react/') ||
                id.includes('/react-dom/') ||
                id.includes('/scheduler/')
              )
                return 'react-vendor';
              return undefined;
            },
          },
        },
      },
    },
    defineVitestConfig({
      test: {
        globals: true,
        environment: 'jsdom',
        testTimeout: 20_000,
        setupFiles: ['./src/test/setup.ts'],
        include: ['src/**/*.{test,spec}.{ts,tsx}'],
        coverage: {
          reporter: ['text', 'json', 'html'],
          exclude: ['node_modules/', 'src/test/'],
        },
      },
    }),
  );
});
