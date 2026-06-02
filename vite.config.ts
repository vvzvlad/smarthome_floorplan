import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

import { execSync } from 'child_process';

// Stamp the build with the git version. `.git` is absent in the Docker build
// context, so fall back to the APP_VERSION env var or 'dev' instead of crashing.
let commitHash = 'dev';
try {
  commitHash = execSync('git describe --tags --always').toString().trim();
} catch {
  commitHash = process.env.APP_VERSION ?? 'dev';
}

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',          // injects SW registration into index.html; no change to main.ts needed
      includeAssets: ['apple-touch-icon-default.png', 'favicon.svg'],
      manifest: {
        name: 'Home Assistant Floor Plan',
        short_name: 'Floor Plan',
        description: 'Interactive Home Assistant floorplan',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
  define: {
    __APP_VERSION__: JSON.stringify(commitHash)
  },
  build: {
    sourcemap: true
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/apple-touch-icon.png': { target: 'http://localhost:8000', changeOrigin: true },
    }
  }
})
