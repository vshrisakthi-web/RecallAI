/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // RecallAI privacy-first palette (from approved Overview design)
        canvas: '#f4f4fb', // app background (soft lavender)
        surface: '#ffffff', // cards / sidebar
        ink: {
          DEFAULT: '#1e1b4b', // indigo-950-ish headings
          muted: '#6b7280', // grey-500 secondary text
        },
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1', // indigo-500 primary accent
          600: '#5b53e8',
          700: '#4f46e5', // indigo-600 active nav
        },
        safe: {
          // "local / on-device" positive indicator (emerald)
          50: '#ecfdf5',
          100: '#d1fae5',
          500: '#10b981',
          700: '#047857',
        },
        warn: {
          50: '#fffbeb',
          100: '#fef3c7',
          500: '#f59e0b',
          700: '#b45309',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
      },
      boxShadow: {
        card: '0 1px 2px rgba(30, 27, 75, 0.04), 0 4px 16px rgba(30, 27, 75, 0.06)',
      },
    },
  },
  plugins: [],
};
