import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from 'tailwindcss';
import autoprefixer from 'autoprefixer';
import { fileURLToPath } from 'node:url';

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));

/**
 * Chrome extensions can't fetch cross-origin local resources, and the
 * `crossorigin` attribute Vite adds breaks extension-page loads. Strip it.
 */
function stripCrossorigin(): Plugin {
  return {
    name: 'strip-crossorigin',
    enforce: 'post',
    transformIndexHtml(html) {
      return html.replace(/\s+crossorigin(?==|\s|>)/g, '');
    },
  };
}

/**
 * Builds the extension POPUP (React + HTML + Tailwind) into
 * extension/.stage/popup/. `root` is pinned to the extension dir and `base` is
 * relative so the popup loads its assets from within the extension package.
 */
export default defineConfig({
  root: here('.'),
  base: './',
  plugins: [react(), stripCrossorigin()],
  css: {
    postcss: {
      plugins: [tailwindcss({ config: here('./tailwind.config.js') }), autoprefixer()],
    },
  },
  build: {
    outDir: here('./.stage'),
    emptyOutDir: false,
    rollupOptions: {
      input: here('./popup/popup.html'),
    },
  },
});


