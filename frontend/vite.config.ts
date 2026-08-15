import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

const rootEnvDir = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, rootEnvDir, '')
  const supabaseTarget = env.SUPABASE_URL || env.VITE_SUPABASE_URL
  return {
    plugins: [react()],
    envDir: rootEnvDir,
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: supabaseTarget
        ? {
            '/api': {
              target: 'http://127.0.0.1:8000',
              changeOrigin: true,
            },
            '/supabase': {
              target: supabaseTarget,
              changeOrigin: true,
              secure: true,
              rewrite: (path) => path.replace(/^\/supabase/, ''),
            },
          }
        : {
            '/api': {
              target: 'http://127.0.0.1:8000',
              changeOrigin: true,
            },
          },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      globals: true,
    },
  }
})
