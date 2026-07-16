#!/usr/bin/env node
/**
 * Static checks for desktop usability acceptance criteria (no Electron GUI).
 * Exit 0 on pass; prints a checklist report.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const failures = [];
const passes = [];

function check(name, cond, detail = '') {
  if (cond) passes.push(`PASS  ${name}${detail ? ` — ${detail}` : ''}`);
  else failures.push(`FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
}

const mainTs = fs.readFileSync(path.join(root, 'desktop/electron/src/main.ts'), 'utf8');
check('activate uses reopenMainWindow', mainTs.includes('reopenMainWindow()'));
check('activate does not call start()', !/activate[\s\S]*desktopApp\.start\(/.test(mainTs));

const appTs = fs.readFileSync(
  path.join(root, 'desktop/electron/src/app/leagent-desktop-app.ts'),
  'utf8',
);
check('reopenMainWindow defined', appTs.includes('async reopenMainWindow'));
check('IPC registerIpcOnce guard', appTs.includes('registerIpcOnce'));

const builder = fs.readFileSync(
  path.join(root, 'desktop/electron/electron-builder.yml'),
  'utf8',
);
check('afterSign wired', /afterSign:\s*build\/notarize\.mjs/.test(builder));
check('asarUnpack removed', !builder.includes('asarUnpack'));
check('mac.notarize false', /notarize:\s*false/.test(builder));

const buildMac = fs.readFileSync(path.join(root, 'desktop/scripts/build-mac.sh'), 'utf8');
check(
  'build-mac does not bake VITE_API_BASE_URL',
  !/export VITE_API_BASE_URL=/.test(buildMac),
);
check('build-mac does not call notarize.mjs standalone', !/node .*notarize\.mjs/.test(buildMac));

const buildLinux = fs.readFileSync(path.join(root, 'desktop/scripts/build-linux.sh'), 'utf8');
check('build-linux does not bake VITE_API_BASE_URL', !/export VITE_API_BASE_URL=/.test(buildLinux));

const buildWin = fs.readFileSync(path.join(root, 'desktop/scripts/build-win.ps1'), 'utf8');
check(
  'build-win does not set VITE_API_BASE_URL',
  !/\$env:VITE_API_BASE_URL\s*=/.test(buildWin),
);

const ci = fs.readFileSync(path.join(root, '.github/workflows/desktop-release.yml'), 'utf8');
check('CI does not set VITE_API_BASE_URL', !/VITE_API_BASE_URL/.test(ci));

const about = fs.readFileSync(
  path.join(root, 'frontend/src/components/layout/AboutDialog.tsx'),
  'utf8',
);
check('About uses updateAvailable', about.includes('r.updateAvailable'));

const backend = fs.readFileSync(
  path.join(root, 'desktop/electron/src/server/backend-server.ts'),
  'utf8',
);
check('waitForHealth clears timeout in finally', /waitForHealth[\s\S]*finally\s*\{[\s\S]*clearTimeout/.test(backend));
check('spawn error sets backendExit', /process\.on\('error'[\s\S]*backendExit/.test(backend));

const maint = fs.readFileSync(
  path.join(root, 'desktop/electron/maintenance/maintenance.js'),
  'utf8',
);
check('maintenance avoids innerHTML for messages', !/innerHTML\s*=\s*'<strong>'/.test(maint));
check('maintenance uses textContent for label', maint.includes('labelEl.textContent'));

const prepare = fs.readFileSync(path.join(root, 'desktop/scripts/prepare-runtime.mjs'), 'utf8');
check('uv path uses aarch64-apple-darwin map', prepare.includes('uv-aarch64-apple-darwin'));

console.log('\n=== Desktop acceptance static checks ===\n');
for (const line of passes) console.log(line);
for (const line of failures) console.log(line);
console.log(`\n${passes.length} passed, ${failures.length} failed\n`);
process.exit(failures.length ? 1 : 0);
