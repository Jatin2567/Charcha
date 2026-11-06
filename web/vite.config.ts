import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: process.env.CHARCHA_API_TARGET || process.env.ARTHA_API_TARGET || 'http://127.0.0.1:8000', ws: true },
    },
  },
  build: { sourcemap: false },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
