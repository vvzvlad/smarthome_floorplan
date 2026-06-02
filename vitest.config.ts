import { defineConfig, defaultExclude } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// Dedicated Vitest config. Kept separate from vite.config.ts on purpose:
// vite.config.ts runs `execSync('git describe')` and loads the PWA plugin,
// neither of which we want pulled into the test runtime.
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.ts'],
    exclude: [...defaultExclude, 'e2e/**'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
    },
  },
})
