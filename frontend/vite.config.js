import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../templates',
    emptyOutDir: true,
    assetsDir: 'static',
    rollupOptions: {
      output: {
        entryFileNames: 'static/index.js',
        chunkFileNames: 'static/[name].js',
        assetFileNames: 'static/[name].[ext]',
      },
    },
  },
  base: '/',
})
