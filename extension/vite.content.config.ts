import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));

/**
 * Builds the extension CONTENT SCRIPT as a self-contained IIFE bundle.
 * A content script is injected as a single file and cannot import sibling
 * chunks, so we inline all of its (shared lib) imports into one output file.
 *
 *   content/contentScript.ts -> dist-extension/content/contentScript.js
 */
export default defineConfig({
  build: {
    outDir: here('./.stage'),
    emptyOutDir: false,
    lib: {
      entry: here('./content/contentScript.ts'),
      formats: ['iife'],
      name: 'RecallAIContent',
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'content/contentScript.js',
      },
    },
  },
});

