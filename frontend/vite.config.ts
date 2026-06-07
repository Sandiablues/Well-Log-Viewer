import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// WL-BUILD-001 scaffold — minimal Vite config
// @vitejs/plugin-react added to devDependencies alongside this file.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
  },
});
