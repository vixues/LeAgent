import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/** Directory containing compiled main-process modules (`dist/`). */
export function distDir(): string {
  return __dirname;
}

export function preloadPath(): string {
  return path.join(__dirname, 'preload.js');
}
