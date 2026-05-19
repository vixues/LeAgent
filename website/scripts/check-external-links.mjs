#!/usr/bin/env node
/**
 * Scan website source for external https?:// URLs and verify they respond.
 * Usage: npm run check:links
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(new URL("..", import.meta.url)));
const SCAN_DIRS = [join(ROOT, "src"), ROOT];
const SCAN_FILES = ["index.html"];
const URL_RE = /https?:\/\/[^\s"'`)>\]]+/g;
const SKIP_SUFFIX = [".test.", ".spec."];
const TIMEOUT_MS = 15_000;

/** Origins used only for preconnect; root URL does not respond to HTTP probes. */
const SKIP_URLS = new Set([
  "https://fonts.googleapis.com",
  "https://fonts.gstatic.com",
]);

/** Unavailable until the repo is public or install scripts are deployed to the site root. */
const WARN_ONLY = [
  /^https:\/\/github\.com\/vixues\/LeAgent(\/|$)/,
  /^https:\/\/vixues\.com\.cn\/install\.(sh|ps1|bat)$/,
];

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const st = statSync(path);
    if (st.isDirectory()) {
      if (name === "node_modules" || name === "_legacy") continue;
      walk(path, out);
    } else if (/\.(tsx?|html|css)$/.test(name) && !SKIP_SUFFIX.some((s) => name.includes(s))) {
      out.push(path);
    }
  }
  return out;
}

function collectUrls() {
  const files = [
    ...SCAN_FILES.map((f) => join(ROOT, f)),
    ...walk(join(ROOT, "src")),
  ];
  const found = new Map();

  for (const file of files) {
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(URL_RE)) {
      let url = match[0].replace(/[.,;]+$/, "");
      if (url.includes("${")) continue;
      // Resolve install-script URLs from content.ts defaults for deploy verification
      if (url === "https://vixues.com.cn") {
        found.set("https://vixues.com.cn/install.sh", [
          ...(found.get("https://vixues.com.cn/install.sh") ?? []),
          relative(ROOT, file) + " (install.sh)",
        ]);
      }
      found.set(url, [...(found.get(url) ?? []), relative(ROOT, file)]);
    }
  }
  return found;
}

async function probe(url) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    for (const method of ["HEAD", "GET"]) {
      const res = await fetch(url, {
        method,
        redirect: "follow",
        signal: ctrl.signal,
        headers: { "User-Agent": "LeAgent-website-link-check/1.0" },
      });
      if (res.ok || (res.status >= 300 && res.status < 400)) {
        return { ok: true, status: res.status, method };
      }
      if (res.status !== 405 && res.status !== 501) {
        return { ok: false, status: res.status, method };
      }
    }
    return { ok: false, status: "no-response", method: "HEAD/GET" };
  } catch (err) {
    return { ok: false, status: err.name === "AbortError" ? "timeout" : String(err.message), method: "-" };
  } finally {
    clearTimeout(timer);
  }
}

const urls = collectUrls();
const entries = [...urls.entries()].sort(([a], [b]) => a.localeCompare(b));

console.log(`Checking ${entries.length} unique external URL(s)...\n`);

let failed = 0;
let skipped = 0;
let warned = 0;
for (const [url, sources] of entries) {
  if (SKIP_URLS.has(url)) {
    skipped += 1;
    console.log(`SKIP  preconnect-only  ${url}`);
    console.log(`      via ${sources[0]}`);
    continue;
  }
  const result = await probe(url);
  const warnOnly = !result.ok && WARN_ONLY.some((re) => re.test(url));
  const tag = result.ok ? "OK  " : warnOnly ? "WARN" : "FAIL";
  if (!result.ok && !warnOnly) failed += 1;
  if (warnOnly) warned += 1;
  const src = sources.slice(0, 2).join(", ") + (sources.length > 2 ? ` +${sources.length - 2}` : "");
  console.log(`${tag}  ${result.status}  ${url}`);
  console.log(`      via ${src}`);
}

console.log(
  `\n${entries.length - failed - skipped - warned} passed, ${failed} failed, ${warned} warned, ${skipped} skipped`,
);
process.exit(failed > 0 ? 1 : 0);
