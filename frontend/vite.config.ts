import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

const localPath = (relative: string) => fileURLToPath(new URL(relative, import.meta.url))
const host = process.env.HOST || '0.0.0.0'
const port = Number(process.env.PORT || 8443)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: '@', replacement: localPath('./src') },
      { find: '@notifyc', replacement: localPath('../deepspace/src') },
      { find: 'deepspace/schema', replacement: localPath('../deepspace/node_modules/deepspace/dist/schema.js') },
      { find: 'deepspace', replacement: localPath('../deepspace/node_modules/deepspace/dist/index.js') },
    ],
    dedupe: ['react', 'react-dom'],
  },
  server: {
    host,
    port,
    strictPort: true,
    fs: { allow: [localPath('..')] },
    proxy: {
      '/api/local/cv-events/notify-first': {
        target: 'http://127.0.0.1:8788',
        changeOrigin: true,
        rewrite: () => '/notify-first',
      },
      '/api': { target: 'http://127.0.0.1:5173', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:5173', ws: true, changeOrigin: true },
    },
  },
  preview: { host, port },
})
