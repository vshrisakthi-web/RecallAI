import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));

/**
 * Builds the extension BACKGROUND SERVICE WORKER as a self-contained IIFE
 * bundle. MV3 service workers are loaded as a single file, so we inline all of
 * its (shared lib) imports into one output file.
 *
 *   background/serviceWorker.ts -> dist-extension/background/serviceWorker.js
 */
export default defineConfig({
  build: {
    outDir: here('./.stage'),
    emptyOutDir: false,
    lib: {
      entry: here('./background/serviceWorker.ts'),
      formats: ['iife'],
      name: 'RecallAIBackground',
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'background/serviceWorker.js',
      },
    },
  },
});
