import fs from 'node:fs';
import path from 'node:path';
import { app } from 'electron';

/** True when path is inside the application install directory. */
export function isInsideAppInstallDir(targetPath: string): boolean {
  const exe = path.dirname(app.getPath('exe'));
  const resolved = path.resolve(targetPath);
  const relative = path.relative(exe, resolved);
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative);
}

/** True when path is under a known cloud-sync folder (OneDrive, iCloud Drive). */
export function isCloudSyncedPath(targetPath: string): boolean {
  const normalized = path.resolve(targetPath).toLowerCase();
  const markers = [
    'onedrive',
    'icloud drive',
    'icloudrive',
    'dropbox',
    'google drive',
  ];
  return markers.some((m) => normalized.includes(m));
}

/** True when directory exists and is writable. */
export function isDirectoryWritable(dirPath: string): boolean {
  try {
    fs.mkdirSync(dirPath, { recursive: true });
    const probe = path.join(dirPath, `.write-test-${process.pid}`);
    fs.writeFileSync(probe, 'ok');
    fs.unlinkSync(probe);
    return true;
  } catch {
    return false;
  }
}

/** Free bytes on the volume containing dirPath (best effort). */
export function getFreeDiskBytes(dirPath: string): number | null {
  try {
    fs.mkdirSync(dirPath, { recursive: true });
    const { bavail, bsize } = fs.statfsSync(dirPath);
    return bavail * bsize;
  } catch {
    return null;
  }
}
