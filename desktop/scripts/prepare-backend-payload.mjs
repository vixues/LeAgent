#!/usr/bin/env node
/**
 * Copies the backend source into desktop/electron/resources/backend-payload/
 * minus .venv, tests, __pycache__, .pytest_cache, etc.
 *
 * Usage:
 *   node prepare-backend-payload.mjs
 */
import fs from 'node:fs';
import path from 'node:path';

const REPO = path.resolve(import.meta.dirname, '..', '..');
const SRC = path.join(REPO, 'backend');
const DEST = path.join(REPO, 'desktop', 'electron', 'resources', 'backend-payload');
const ROOT_CONFIG = path.join(REPO, 'config');

const INCLUDE = [
  'leagent',
  'alembic',
  'pyproject.toml',
  'uv.lock',
  'alembic.ini',
  'README.md',
];

const EXCLUDE_DIRS = new Set([
  '__pycache__',
  '.pytest_cache',
  '.mypy_cache',
  '.ruff_cache',
  '.venv',
  'node_modules',
  'tests',
  '.git',
  '.eggs',
  '*.egg-info',
]);

const EXCLUDE_PATTERNS = [/\.pyc$/, /\.pyo$/, /\.egg-info$/, /~$/];

function shouldExclude(name) {
  if (EXCLUDE_DIRS.has(name)) return true;
  if (name.endsWith('.egg-info')) return true;
  return false;
}

function shouldExcludeFile(name) {
  return EXCLUDE_PATTERNS.some((p) => p.test(name));
}

function copyRecursive(src, dest) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    const name = path.basename(src);
    if (shouldExclude(name)) return;
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src)) {
      copyRecursive(path.join(src, entry), path.join(dest, entry));
    }
  } else {
    const name = path.basename(src);
    if (shouldExcludeFile(name)) return;
    fs.copyFileSync(src, dest);
  }
}

function main() {
  console.log('Preparing backend payload…');
  console.log(`  Source:      ${SRC}`);
  console.log(`  Destination: ${DEST}`);

  if (fs.existsSync(DEST)) {
    console.log('  Cleaning previous payload…');
    fs.rmSync(DEST, { recursive: true, force: true });
  }
  fs.mkdirSync(DEST, { recursive: true });

  let copied = 0;
  for (const entry of INCLUDE) {
    const srcPath = path.join(SRC, entry);
    const destPath = path.join(DEST, entry);
    if (!fs.existsSync(srcPath)) {
      console.warn(`  ⚠ Skipping missing: ${entry}`);
      continue;
    }
    copyRecursive(srcPath, destPath);
    copied++;
    console.log(`  ✓ ${entry}`);
  }

  const templatesSrc = path.join(ROOT_CONFIG, 'workflows', 'templates');
  if (fs.existsSync(templatesSrc)) {
    copyRecursive(
      templatesSrc,
      path.join(DEST, 'config', 'workflows', 'templates'),
    );
    copied++;
    console.log('  ✓ config/workflows/templates');
  } else {
    console.warn('  ⚠ Skipping missing: config/workflows/templates');
  }

  console.log(`\nDone. ${copied} entries staged.`);
}

main();
