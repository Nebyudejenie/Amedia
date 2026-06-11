import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  // Cast needed: vitest bundles its own vite, whose Plugin type conflicts
  // with the copy @vitejs/plugin-react was compiled against.
  plugins: [react() as never],
  test: {
    environment: 'jsdom',
    setupFiles: ['./__tests__/setup.ts'],
    globals: true,
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, './') },
  },
});
