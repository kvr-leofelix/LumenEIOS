import path from 'path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  // The API tests mock this absolute base URL; pin it so they do not depend on the runtime default (same-origin /api/v1).
  define: { 'import.meta.env.VITE_API_URL': JSON.stringify('http://localhost:8000/api/v1') },
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
