import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

import { execSync } from 'child_process';

let commitHash = 'dev';
try {
  commitHash = execSync('git describe --tags --always').toString().trim();
} catch {
  // git not available (e.g. Docker build without .git)
}

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [vue()],
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
      }
    }
  }
})
