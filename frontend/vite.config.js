import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,  // Vite's default port (different from gateway:8787)
    host: '0.0.0.0', // Allow external connections
    open: true,
    cors: true, // Enable CORS for Builder.io
    // Force reload on file changes to prevent stale modules
    hmr: {
      overlay: true
    },
    watch: {
      usePolling: true // Better file watching in WSL/Docker environments
    },
    proxy: {
      // All API routes go through the Gateway (Express) at port 8787
      // The Gateway then routes to FastAPI backend at port 8000
      '/api': {
        target: 'http://localhost:8787',
        changeOrigin: true,
        secure: false,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('Proxying:', req.method, req.url, '→', options.target + req.url);
          });
          proxy.on('proxyRes', (proxyRes, req, res) => {
            console.log('Proxy response:', proxyRes.statusCode, req.url);
          });
        }
      },
      '/ws': {
        target: 'ws://localhost:8787', // Proxy WebSocket to gateway
        ws: true,
        changeOrigin: true,
        secure: false
      }
    }
  },
  // Disable aggressive caching during development
  cacheDir: 'node_modules/.vite',
  optimizeDeps: {
    force: false // Don't force re-optimization on every restart
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('react-router-dom')) {
            return 'router'
          }
          if (
            id.includes('/react/') ||
            id.includes('\\react\\') ||
            id.includes('/react-dom/') ||
            id.includes('\\react-dom\\')
          ) {
            return 'react-vendor'
          }
          if (
            id.includes('node_modules/three') ||
            id.includes('node_modules/pixi.js')
          ) {
            return 'graphics-vendor'
          }
          if (
            id.includes('ArcadeVisualizer') ||
            id.includes('arcade-visualizer') ||
            id.includes('ArcadeButtonGrid') ||
            id.includes('ButtonGrid')
          ) {
            return 'arcade-visualizer'
          }
          if (id.includes('@supabase') || id.includes('supabase-js')) {
            return 'supabase-vendor'
          }
        }
      }
    }
  }
})
