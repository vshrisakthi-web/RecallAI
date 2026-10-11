// RecallAI — extension icon generator (Module 2, Task 2.2)
//
// Writes valid PNG icons (16/48/128) into extension/assets/ without any image
// dependency. Draws a simple indigo rounded-square with a white "refresh" glyph
// using a minimal, dependency-free PNG encoder (zlib is built into Node).
//
// Run: npm run icons:extension

import { deflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = (p) => dirname(fileURLToPath(import.meta.url));
const assetsDir = resolve(here('.'), '..', 'assets');

// --- CRC32 (PNG uses CRC-32 over chunk type + data) --------------------------
const crcTable = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = crcTable[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, 'ascii');
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crc]);
}

/** Encode raw RGBA pixels (size*size*4) as a PNG buffer. */
function encodePng(size, rgba) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  // bytes 10-12 are 0 (compression, filter, interlace)
  // Add a filter byte (0) at the start of each row.
  const stride = size * 4;
  const raw = Buffer.alloc((stride + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (stride + 1)] = 0;
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
  }
  const idat = deflateSync(raw, { level: 9 });
  return Buffer.concat([sig, chunk('IHDR', ihdr), chunk('IDAT', idat), chunk('IEND', Buffer.alloc(0))]);
}

/** Draw the RecallAI mark for a given square size. */
function drawIcon(size) {
  const rgba = Buffer.alloc(size * size * 4, 0);
  const indigo = [79, 70, 229]; // #4f46e5
  const white = [255, 255, 255];
  const r = Math.floor(size * 0.22); // corner radius
  const cx = size / 2;
  const cy = size / 2;
  const armR = size * 0.3; // glyph outer radius
  const armW = Math.max(1, size * 0.11); // stroke width

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const nearLeft = x < r;
      const nearRight = x >= size - r;
      const nearTop = y < r;
      const nearBottom = y >= size - r;
      // Rounded-rectangle containment test.
      const inCorner = (nearLeft || nearRight) && (nearTop || nearBottom);
      let inside = true;
      if (inCorner) {
        const ccx = nearLeft ? r : size - r;
        const ccy = nearTop ? r : size - r;
        const ddx = x - ccx;
        const ddy = y - ccy;
        inside = ddx * ddx + ddy * ddy <= r * r;
      }
      if (!inside) continue;

      const i = (y * size + x) * 4;
      let color = indigo;

      // White circular-arrow glyph: a ring with a gap at the upper-right.
      const dx = x - cx;
      const dy = y - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const onRing = dist <= armR && dist >= armR - armW;
      const angle = Math.atan2(dy, dx); // -PI..PI
      const inGap = angle > -1.9 && angle < -1.1; // upper-right opening
      if (onRing && !inGap) color = white;

      rgba[i] = color[0];
      rgba[i + 1] = color[1];
      rgba[i + 2] = color[2];
      rgba[i + 3] = 255;
    }
  }
  return encodePng(size, rgba);
}

mkdirSync(assetsDir, { recursive: true });
for (const size of [16, 48, 128]) {
  const file = resolve(assetsDir, `icon${size}.png`);
  writeFileSync(file, drawIcon(size));
  console.log(`wrote ${file}`);
}
console.log('Icons generated in', assetsDir);
