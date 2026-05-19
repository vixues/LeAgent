#!/usr/bin/env node
/**
 * Converts the SVG logo to .icns / .ico / .png for Electron packaging.
 *
 * Requires: sharp (npm i -D sharp)
 *
 * Usage:
 *   node make-icons.mjs [--source path/to/logo.svg]
 *
 * Outputs:
 *   desktop/electron/resources/icons/icon.png   (1024x1024)
 *   desktop/electron/resources/icons/icon.ico   (multi-size)
 *   desktop/electron/resources/icons/tray.png   (32x32)
 *   desktop/electron/resources/icons/icon.icns  (macOS — requires png2icns or iconutil on macOS)
 */
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const REPO = path.resolve(import.meta.dirname, '..', '..');
const APP_ICON_SVG = path.join(REPO, 'desktop', 'electron', 'resources', 'app-icon.svg');
const FAVICON_SVG = path.join(REPO, 'frontend', 'public', 'favicon.svg');
const DEFAULT_SVG = fs.existsSync(APP_ICON_SVG) ? APP_ICON_SVG : FAVICON_SVG;
const OUT_DIR = path.join(REPO, 'desktop', 'electron', 'resources', 'icons');

function parseArgs() {
  const idx = process.argv.indexOf('--source');
  return idx !== -1 && process.argv[idx + 1]
    ? path.resolve(process.argv[idx + 1])
    : DEFAULT_SVG;
}

async function main() {
  const svgPath = parseArgs();
  if (!fs.existsSync(svgPath)) {
    console.error(`SVG not found: ${svgPath}`);
    process.exit(1);
  }
  console.log(`Source SVG: ${svgPath}`);
  fs.mkdirSync(OUT_DIR, { recursive: true });

  let sharp;
  try {
    sharp = (await import('sharp')).default;
  } catch {
    try {
      const modulePath = path.join(REPO, 'desktop', 'electron', 'node_modules', 'sharp', 'lib', 'index.js');
      sharp = (await import(modulePath)).default;
    } catch {
      console.error(
        'sharp is required. Install it in desktop/electron:\n  cd desktop/electron && npm i -D sharp',
      );
      process.exit(1);
    }
  }

  const svgBuf = fs.readFileSync(svgPath);

  // 1024x1024 main PNG
  const png1024 = path.join(OUT_DIR, 'icon.png');
  await sharp(svgBuf)
    .resize(1024, 1024, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toFile(png1024);
  console.log(`  ✓ ${png1024}`);

  // Tray icon 32x32
  const tray = path.join(OUT_DIR, 'tray.png');
  await sharp(svgBuf)
    .resize(32, 32, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toFile(tray);
  console.log(`  ✓ ${tray}`);

  // ICO (multi-size: 16, 24, 32, 48, 64, 128, 256)
  const icoSizes = [16, 24, 32, 48, 64, 128, 256];
  const icoPngs = [];
  const tmpDir = path.join(OUT_DIR, '_ico_tmp');
  fs.mkdirSync(tmpDir, { recursive: true });

  for (const size of icoSizes) {
    const p = path.join(tmpDir, `icon_${size}.png`);
    await sharp(svgBuf)
      .resize(size, size, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .png()
      .toFile(p);
    icoPngs.push(p);
  }

  // Use png-to-ico if available, otherwise fall back to the 256px PNG
  const icoPath = path.join(OUT_DIR, 'icon.ico');
  let pngToIco;
  try {
    pngToIco = (await import('png-to-ico')).default;
  } catch {
    try {
      const electronPkgDir = path.join(REPO, 'desktop', 'electron');
      const modulePath = path.join(electronPkgDir, 'node_modules', 'png-to-ico', 'index.js');
      pngToIco = (await import(modulePath)).default;
    } catch { /* not available */ }
  }
  if (pngToIco) {
    const buffers = icoPngs.map((p) => fs.readFileSync(p));
    const ico = await pngToIco(buffers);
    fs.writeFileSync(icoPath, ico);
    console.log(`  ✓ ${icoPath} (multi-size)`);
  } else {
    fs.copyFileSync(path.join(tmpDir, 'icon_256.png'), icoPath);
    console.log(`  ⚠ ${icoPath} (single 256px — install png-to-ico in desktop/electron for multi-size)`);
  }

  fs.rmSync(tmpDir, { recursive: true, force: true });

  // ICNS (macOS) — try iconutil (macOS only) or png2icns
  if (process.platform === 'darwin') {
    const icnsDir = path.join(OUT_DIR, 'icon.iconset');
    fs.mkdirSync(icnsDir, { recursive: true });
    const icnsSizes = [16, 32, 64, 128, 256, 512, 1024];
    for (const size of icnsSizes) {
      const name = size === 1024 ? 'icon_512x512@2x.png' : `icon_${size}x${size}.png`;
      await sharp(svgBuf)
        .resize(size, size, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
        .png()
        .toFile(path.join(icnsDir, name));
      if (size <= 512) {
        const name2x = `icon_${size}x${size}@2x.png`;
        await sharp(svgBuf)
          .resize(size * 2, size * 2, {
            fit: 'contain',
            background: { r: 0, g: 0, b: 0, alpha: 0 },
          })
          .png()
          .toFile(path.join(icnsDir, name2x));
      }
    }
    try {
      const icnsPath = path.join(OUT_DIR, 'icon.icns');
      execSync(`iconutil -c icns "${icnsDir}" -o "${icnsPath}"`, { stdio: 'inherit' });
      console.log(`  ✓ ${icnsPath}`);
    } catch {
      console.log('  ⚠ iconutil failed — .icns not generated (macOS only)');
    }
    fs.rmSync(icnsDir, { recursive: true, force: true });
  } else {
    console.log('  ℹ Skipping .icns generation (not on macOS)');
  }

  console.log('\nDone.');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
