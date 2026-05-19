// Removes second-string fallback from t('key', 'fallback') and t('key', 'fallback', opts)
// so literals live only in JSON. Run: node scripts/strip-i18n-fallback-args.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, '..');
const srcRoot = path.join(root, 'src');

function walk(dir, acc = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ent.name.startsWith('.')) continue;
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      if (ent.name === 'node_modules' || ent.name === 'dist') continue;
      walk(p, acc);
    } else if (ent.isFile() && (ent.name.endsWith('.tsx') || ent.name.endsWith('.ts'))) {
      if (p.includes(`${path.sep}i18n${path.sep}locales${path.sep}`)) continue;
      acc.push(p);
    }
  }
  return acc;
}

function strip(content) {
  let s = content;
  // t('key', 'fallback', { ... }) -> t('key', { ... })
  s = s.replace(/\bt(\s*)\(\s*((?:'(?:\\.|[^'])*'|"(?:\\.|[^"])*"))\s*,\s*(?:'(?:\\.|[^'])*'|"(?:\\.|[^"])*")\s*,/g, 't$1($2,');
  // t('key', 'fallback') -> t('key')
  s = s.replace(/\bt(\s*)\(\s*((?:'(?:\\.|[^'])*'|"(?:\\.|[^"])*"))\s*,\s*(?:'(?:\\.|[^'])*'|"(?:\\.|[^"])*")\s*\)/g, 't$1($2)');
  return s;
}

let n = 0;
for (const file of walk(srcRoot)) {
  const before = fs.readFileSync(file, 'utf8');
  const after = strip(before);
  if (after !== before) {
    fs.writeFileSync(file, after);
    n++;
  }
}
console.log('updated files:', n);
