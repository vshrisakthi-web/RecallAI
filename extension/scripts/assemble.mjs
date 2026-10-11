// RecallAI — assemble the loadable extension directory (Module 2, Task 2.1)
//
// Produces extension/dist-extension/ as a clean, Chrome-loadable directory by
// combining:
//   - the built outputs staged in extension/.stage/ (popup/, content/, background/),
//   - the manifest.json,
//   - the generated icons in extension/assets/.
//
// Safe to re-run: it wipes dist-extension first, then copies everything fresh, so
// no stale files linger. Run AFTER the three Vite builds (which write to .stage/).

import { cp, mkdir, rm } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = (p) => dirname(fileURLToPath(import.meta.url));
const extRoot = resolve(here('.'), '..');
const stage = resolve(extRoot, '.stage');
const dist = resolve(extRoot, 'dist-extension');

// 1. Clean the final directory.
await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

// 2. Copy built outputs (popup, content, background) from staging.
for (const sub of ['popup', 'content', 'background']) {
  await cp(resolve(stage, sub), resolve(dist, sub), { recursive: true });
}

// 2b. Copy Vite-emitted shared assets (popup JS/CSS) if present.
await cp(resolve(stage, 'assets'), resolve(dist, 'assets'), { recursive: true, force: true }).catch(() => {});

// 3. Manifest + icons (icons merge into assets/ alongside Vite's built files).
await cp(resolve(extRoot, 'manifest.json'), resolve(dist, 'manifest.json'));
await cp(resolve(extRoot, 'assets'), resolve(dist, 'assets'), { recursive: true });

console.log('Assembled loadable extension at:', dist);

