#!/usr/bin/env node
/**
 * Downloads python-build-standalone and uv per platform into
 * desktop/electron/resources/runtime/<platform-arch>/
 *
 * Usage:
 *   node prepare-runtime.mjs --platform win-x64
 *   node prepare-runtime.mjs --platform mac-arm64,mac-x64
 *   node prepare-runtime.mjs                             # current host
 */
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pipeline } from 'node:stream/promises';
import { createWriteStream } from 'node:fs';

const PYTHON_VERSION = '3.12.8';
const PYTHON_BUILD_STANDALONE_TAG = '20241219';
const UV_VERSION = '0.5.14';

const TARGETS = {
  'win-x64': {
    pythonArchive: `cpython-${PYTHON_VERSION}+${PYTHON_BUILD_STANDALONE_TAG}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz`,
    uvArchive: `uv-x86_64-pc-windows-msvc.zip`,
    uvBin: 'uv.exe',
  },
  'mac-arm64': {
    pythonArchive: `cpython-${PYTHON_VERSION}+${PYTHON_BUILD_STANDALONE_TAG}-aarch64-apple-darwin-install_only_stripped.tar.gz`,
    uvArchive: `uv-aarch64-apple-darwin.tar.gz`,
    uvBin: 'uv',
  },
  'mac-x64': {
    pythonArchive: `cpython-${PYTHON_VERSION}+${PYTHON_BUILD_STANDALONE_TAG}-x86_64-apple-darwin-install_only_stripped.tar.gz`,
    uvArchive: `uv-x86_64-apple-darwin.tar.gz`,
    uvBin: 'uv',
  },
  'linux-x64': {
    pythonArchive: `cpython-${PYTHON_VERSION}+${PYTHON_BUILD_STANDALONE_TAG}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz`,
    uvArchive: `uv-x86_64-unknown-linux-gnu.tar.gz`,
    uvBin: 'uv',
  },
};

const PYTHON_BASE_URL = `https://github.com/indygreg/python-build-standalone/releases/download/${PYTHON_BUILD_STANDALONE_TAG}`;
const UV_BASE_URL = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}`;

const REPO = path.resolve(import.meta.dirname, '..', '..');
const RESOURCES = path.join(REPO, 'desktop', 'electron', 'resources', 'runtime');

function detectHostPlatform() {
  const arch = process.arch === 'arm64' ? 'arm64' : 'x64';
  const plat = process.platform === 'win32' ? 'win' : process.platform === 'linux' ? 'linux' : 'mac';
  return `${plat}-${arch}`;
}

function parseArgs() {
  const idx = process.argv.indexOf('--platform');
  if (idx === -1 || !process.argv[idx + 1]) return [detectHostPlatform()];
  return process.argv[idx + 1].split(',').map((s) => s.trim());
}

async function download(url, dest) {
  console.log(`  ↓ ${url}`);
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${url}`);
  await pipeline(res.body, createWriteStream(dest));
}

async function extract(archive, destDir) {
  if (archive.endsWith('.tar.gz') || archive.endsWith('.tgz')) {
    execSync(`tar xzf "${archive}" -C "${destDir}"`, { stdio: 'inherit' });
  } else if (archive.endsWith('.zip')) {
    if (process.platform === 'win32') {
      execSync(
        `powershell -NoProfile -Command "Expand-Archive -Force '${archive}' '${destDir}'"`,
        { stdio: 'inherit' },
      );
    } else {
      execSync(`unzip -o "${archive}" -d "${destDir}"`, { stdio: 'inherit' });
    }
  }
}

async function prepareTarget(target) {
  const spec = TARGETS[target];
  if (!spec) {
    console.error(`Unknown target: ${target}. Known: ${Object.keys(TARGETS).join(', ')}`);
    process.exit(1);
  }
  const outDir = path.join(RESOURCES, target);
  fs.mkdirSync(outDir, { recursive: true });

  const tmpDir = path.join(outDir, '_tmp');
  fs.mkdirSync(tmpDir, { recursive: true });

  // Python
  const pyDest = path.join(outDir, 'python');
  if (!fs.existsSync(pyDest)) {
    console.log(`\n[${target}] Downloading Python ${PYTHON_VERSION}…`);
    const pyArchive = path.join(tmpDir, spec.pythonArchive);
    await download(`${PYTHON_BASE_URL}/${spec.pythonArchive}`, pyArchive);
    await extract(pyArchive, outDir);
    fs.unlinkSync(pyArchive);
  } else {
    console.log(`[${target}] Python already present, skipping.`);
  }

  // uv
  const uvDest = path.join(outDir, spec.uvBin);
  if (!fs.existsSync(uvDest)) {
    console.log(`[${target}] Downloading uv ${UV_VERSION}…`);
    const uvArchive = path.join(tmpDir, spec.uvArchive);
    await download(`${UV_BASE_URL}/${spec.uvArchive}`, uvArchive);
    await extract(uvArchive, tmpDir);
    // uv archives extract a single binary (or a dir with one)
    const candidates = [
      path.join(tmpDir, spec.uvBin),
      path.join(tmpDir, 'uv', spec.uvBin),
      path.join(tmpDir, `uv-${target.replace('mac', 'aarch64-apple-darwin').replace('win', 'x86_64-pc-windows-msvc')}`, spec.uvBin),
    ];
    const found = candidates.find((c) => fs.existsSync(c));
    if (found) {
      fs.copyFileSync(found, uvDest);
      if (process.platform !== 'win32') fs.chmodSync(uvDest, 0o755);
    } else {
      // Fallback: find uv binary recursively
      const result = execSync(`find "${tmpDir}" -name "${spec.uvBin}" -type f`, {
        encoding: 'utf-8',
      }).trim();
      if (result) {
        fs.copyFileSync(result.split('\n')[0], uvDest);
        if (process.platform !== 'win32') fs.chmodSync(uvDest, 0o755);
      } else {
        console.error(`Could not locate ${spec.uvBin} in extracted archive`);
        process.exit(1);
      }
    }
    fs.unlinkSync(path.join(tmpDir, spec.uvArchive).replace(tmpDir, tmpDir));
  } else {
    console.log(`[${target}] uv already present, skipping.`);
  }

  // Cleanup tmp
  fs.rmSync(tmpDir, { recursive: true, force: true });
  console.log(`[${target}] Done.`);
}

async function main() {
  const targets = parseArgs();
  console.log(`Preparing runtime for: ${targets.join(', ')}`);
  for (const t of targets) {
    await prepareTarget(t);
  }
  console.log('\nAll runtimes staged under:', RESOURCES);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
