module.exports = {
  root: true,
  env: { browser: true, es2021: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['@typescript-eslint', 'react-hooks', 'react-refresh'],
  ignorePatterns: [
    'dist',
    'node_modules',
    '*.config.js',
    '*.config.ts',
    // Extension build output (generated; minified, uses chrome globals).
    'extension/dist-extension',
    'extension/.stage',
    // Extension build orchestration scripts (plain Node ESM).
    'extension/scripts',
  ],
  rules: {
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
    'react-refresh/only-export-components': 'off',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    '@typescript-eslint/no-explicit-any': 'warn',
  },
  overrides: [
    {
      // Extension source uses the `chrome` global (provided by Chrome at runtime).
      files: ['extension/**/*.{ts,tsx}'],
      globals: { chrome: 'readonly' },
    },
    {
      files: ['**/*.test.ts', '**/*.test.tsx'],
      env: { node: true },
    },
  ],
};

