// Scans src for t('key', 'literal') and merges into zh-CN / en-US locale JSON bundles.
// Run: node scripts/extract-i18n-fallbacks.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, '..');
const srcRoot = path.join(root, 'src');
const BUNDLE_DIR = path.join(root, 'src', 'i18n', 'locales');

function walk(dir, acc = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ent.name.startsWith('.')) continue;
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      if (ent.name === 'node_modules' || ent.name === 'dist') continue;
      walk(p, acc);
    } else if (ent.isFile() && (ent.name.endsWith('.tsx') || ent.name.endsWith('.ts'))) {
      if (p.includes(`${path.sep}i18n${path.sep}locales${path.sep}`)) continue;
      if (p.includes(`${path.sep}__tests__${path.sep}`)) continue;
      acc.push(p);
    }
  }
  return acc;
}

function setDeep(obj, keyPath, value) {
  const parts = keyPath.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const k = parts[i];
    if (!cur[k] || typeof cur[k] !== 'object' || Array.isArray(cur[k])) cur[k] = {};
    cur = cur[k];
  }
  cur[parts[parts.length - 1]] = value;
}

function getDeep(obj, keyPath) {
  const parts = keyPath.split('.');
  let cur = obj;
  for (const k of parts) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = cur[k];
  }
  return cur;
}

function flattenLeaves(obj, prefix = '') {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const p = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) Object.assign(out, flattenLeaves(v, p));
    else if (typeof v === 'string') out[p] = v;
  }
  return out;
}

const reS = /\bt\s*\(\s*'([^']+)'\s*,\s*'((?:\\'|[^'])*)'\s*\)/gs;
const reD = /\bt\s*\(\s*"([^"]+)"\s*,\s*"((?:\\"|[^"])*)"\s*\)/gs;

const extracted = {};
const files = walk(srcRoot);
for (const file of files) {
  const s = fs.readFileSync(file, 'utf8');
  for (const r of [reS, reD]) {
    let m;
    while ((m = r.exec(s)) !== null) {
      const key = m[1];
      const raw = m[2].replace(/\\'/g, "'").replace(/\\"/g, '"');
      setDeep(extracted, key, raw);
    }
  }
}

const flatExtracted = flattenLeaves(extracted);

function loadBundle(lng, name) {
  return JSON.parse(fs.readFileSync(path.join(BUNDLE_DIR, lng, `${name}.json`), 'utf8'));
}

function saveBundle(lng, name, data) {
  fs.writeFileSync(path.join(BUNDLE_DIR, lng, `${name}.json`), JSON.stringify(data, null, 2) + '\n');
}

const bundleNames = fs.readdirSync(path.join(BUNDLE_DIR, 'zh-CN')).filter((f) => f.endsWith('.json')).map((f) => f.replace('.json', ''));

function bundleForTopKey(top) {
  for (const bn of bundleNames) {
    const data = loadBundle('zh-CN', bn);
    if (Object.prototype.hasOwnProperty.call(data, top)) return bn;
  }
  /** Keys like `mcp` default to integrations */
  return 'integrations';
}

function patchLng(lng, pickValue) {
  for (const bn of bundleNames) {
    const data = loadBundle(lng, bn);
    let changed = false;
    for (const [flatKey, fb] of Object.entries(flatExtracted)) {
      const top = flatKey.split('.')[0];
      const targetBn = bundleForTopKey(top);
      if (targetBn !== bn) continue;
      if (getDeep(data, flatKey) !== undefined) continue;
      const v = pickValue(flatKey, fb, lng);
      if (v === undefined) continue;
      const parts = flatKey.split('.');
      let cur = data;
      for (let i = 0; i < parts.length - 1; i++) {
        const k = parts[i];
        if (!cur[k] || typeof cur[k] !== 'object' || Array.isArray(cur[k])) cur[k] = {};
        cur = cur[k];
      }
      cur[parts[parts.length - 1]] = v;
      changed = true;
    }
    if (changed) saveBundle(lng, bn, data);
  }
}

patchLng('zh-CN', (_k, fb) => fb);

patchLng('en-US', (flatKey, fb, lng) => {
  const zhVal = getDeep(loadBundle('zh-CN', bundleForTopKey(flatKey.split('.')[0])), flatKey);
  const ascii = /^[\x00-\x7f…]*$/.test(fb) && fb.length > 0;
  if (ascii) return fb;
  if (typeof zhVal === 'string' && /^[\x00-\x7f…]*$/.test(zhVal)) return zhVal;
  return zhVal ?? fb;
});

console.log('extracted', Object.keys(flatExtracted).length, 't() fallback literals');
