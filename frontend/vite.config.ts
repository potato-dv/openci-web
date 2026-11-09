import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_API_PROXY_TARGET')
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000'
  const apiPrefixes = [
    '/users',
    '/investigations',
    '/locations',
    '/activity-logs',
    '/planning',
    '/reports',
    '/agent-permissions',
  ]

  return {
    plugins: [tailwindcss(), react()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      proxy: Object.fromEntries(
        [...apiPrefixes, '/ws'].map((prefix) => [
          prefix,
          {
            target: apiTarget,
            changeOrigin: true,
            ...(prefix === '/ws' ? { ws: true } : {}),
            bypass: (request) =>
              request.headers.accept?.includes('text/html')
                ? request.url
                : undefined,
          },
        ]),
      ),
    },
  }
})
