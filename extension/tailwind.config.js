import { fileURLToPath } from 'node:url';

const here = (p) => fileURLToPath(new URL(p, import.meta.url));

/** Tailwind config for the extension popup (separate from the dashboard). */
export default {
  // Absolute globs so scanning works regardless of the process CWD.
  content: [here('./popup/**/*.{tsx,ts,html}'), here('./popup/popup.html')],
  theme: {
    extend: {
      colors: {
        canvas: '#f4f4fb',
        surface: '#ffffff',
        ink: { DEFAULT: '#1e1b4b', muted: '#6b7280' },
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1',
          600: '#5b53e8',
          700: '#4f46e5',
        },
        safe: { 50: '#ecfdf5', 100: '#d1fae5', 500: '#10b981', 700: '#047857' },
        warn: { 50: '#fffbeb', 100: '#fef3c7', 500: '#f59e0b', 700: '#b45309' },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(30,27,75,0.04), 0 4px 16px rgba(30,27,75,0.06)',
      },
    },
  },
  plugins: [],
};

