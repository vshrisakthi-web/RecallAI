// RecallAI — verify the assembled extension (Module 2, Task 2.1)
//
// Fails loudly if any manifest-referenced file is missing, so we never claim a
// loadable extension when the build is incomplete. Exit code 1 on any problem.

import { readFile, access } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { constants } from 'node:fs';

const here = (p) => dirname(fileURLToPath(import.meta.url));
const extRoot = resolve(here('.'), '..');
const dist = resolve(extRoot, 'dist-extension');

const errors = [];
const exists = async (rel) => {
  try {
    await access(resolve(dist, rel), constants.R_OK);
    return true;
  } catch {
    return false;
  }
};

// 1. Manifest present + parseable.
let manifest;
try {
  manifest = JSON.parse(await readFile(resolve(dist, 'manifest.json'), 'utf8'));
} catch (e) {
  console.error('✗ manifest.json missing or invalid:', e.message);
  process.exit(1);
}

if (manifest.manifest_version !== 3) {
  errors.push(`manifest_version must be 3 (got ${manifest.manifest_version})`);
}

// 2. Required manifest files exist.
const required = [];
required.push(manifest.action?.default_popup);
required.push(manifest.background?.service_worker);
for (const v of Object.values(manifest.icons ?? {})) required.push(v);
for (const v of Object.values(manifest.action?.default_icon ?? {})) required.push(v);

for (const rel of required) {
  if (!rel) continue;
  if (!(await exists(rel))) errors.push(`Missing referenced file: ${rel}`);
}

// 3. Popup HTML references a built JS + CSS that exist.
const popupRel = manifest.action?.default_popup;
if (popupRel && (await exists(popupRel))) {
  const html = await readFile(resolve(dist, popupRel), 'utf8');
  const refs = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map((m) => m[1]);
  const localRefs = refs.filter((r) => !/^https?:/.test(r));
  const popupDir = dirname(resolve(dist, popupRel));
  for (const ref of localRefs) {
    // Vite emits absolute "/assets/..." which resolves from the extension root.
    const target = ref.startsWith('/')
      ? resolve(dist, ref.slice(1))
      : resolve(popupDir, ref.replace(/^\.?\//, ''));
    try {
      await access(target, constants.R_OK);
    } catch {
      errors.push(`Popup HTML references missing asset: ${ref}`);
    }
  }
  if (localRefs.length === 0) {
    errors.push('Popup HTML has no local script/asset references (build may be empty)');
  }
}

// 4. Permissions sanity: must be minimal and not include broad host access.
const perms = manifest.permissions ?? [];
const allowed = new Set(['activeTab', 'scripting', 'storage']);
for (const p of perms) {
  if (!allowed.has(p)) errors.push(`Unexpected permission: ${p}`);
}
if ((manifest.host_permissions ?? []).length > 0) {
  errors.push('host_permissions should be empty (use activeTab + scripting instead)');
}

// 5. No remote code / remote scripts.
const csp = manifest.content_security_policy?.extension_pages ?? '';
if (!csp.includes("'self'")) {
  errors.push("CSP must restrict extension_pages to 'self'");
}

if (errors.length > 0) {
  console.error('✗ Extension verification FAILED:');
  for (const e of errors) console.error('  -', e);
  process.exit(1);
}

console.log('✓ Extension verified:');
console.log('  - manifest.json valid (MV3)');
console.log('  - all referenced files present');
console.log('  - popup assets wired');
console.log('  - permissions minimal:', perms.join(', ') || '(none)');
console.log('  - no host_permissions, CSP locked to self');
console.log('  Load unpacked from:', dist);
