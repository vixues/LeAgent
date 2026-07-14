/**
 * Copy static assets required for a self-contained dist/ deploy.
 * Website markdown (README) references docs/assets/* — these must ship in public/.
 */
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const websiteRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = join(websiteRoot, "..");
const publicRoot = join(websiteRoot, "public");

function copyDir(src, dest, label) {
  if (!existsSync(src)) {
    console.warn(`copy-static-assets: skip missing ${label}: ${src}`);
    return;
  }
  mkdirSync(dirname(dest), { recursive: true });
  cpSync(src, dest, { recursive: true });
  console.log(`copy-static-assets: ${label} -> ${dest}`);
}

// Install scripts at site root
for (const name of ["install.sh", "install.ps1", "install.bat"]) {
  const src = join(repoRoot, "scripts", name);
  const dest = join(publicRoot, name);
  if (existsSync(src)) {
    cpSync(src, dest);
    console.log(`copy-static-assets: ${name}`);
  }
}

// README / intro images: /docs/assets/...
copyDir(
  join(repoRoot, "docs", "assets"),
  join(publicRoot, "docs", "assets"),
  "docs/assets",
);
