import path from 'node:path';
import fs from 'node:fs';
import { app } from 'electron';

const IS_PACKAGED = app.isPackaged;

function resourcesDir(): string {
  if (IS_PACKAGED) {
    return process.resourcesPath;
  }
  return path.join(__dirname, '..', '..', 'resources');
}

function repoRoot(): string {
  return path.resolve(__dirname, '..', '..', '..', '..');
}

function platformKey(): string {
  const arch = process.arch === 'arm64' ? 'arm64' : 'x64';
  const plat = process.platform === 'win32' ? 'win' : process.platform === 'linux' ? 'linux' : 'mac';
  return `${plat}-${arch}`;
}

export function pythonExe(): string {
  const base = path.join(resourcesDir(), 'runtime', platformKey(), 'python');
  if (process.platform === 'win32') {
    return path.join(base, 'python.exe');
  }
  return path.join(base, 'bin', 'python3');
}

export function uvExe(): string {
  const bin = process.platform === 'win32' ? 'uv.exe' : 'uv';
  return path.join(resourcesDir(), 'runtime', platformKey(), bin);
}

export function backendPayloadDir(): string {
  return path.join(resourcesDir(), 'backend-payload');
}

export function backendSourceDir(): string {
  return path.join(repoRoot(), 'backend');
}

export function backendWorkingDir(): string {
  return IS_PACKAGED ? backendPayloadDir() : backendSourceDir();
}

export function frontendDir(): string {
  return path.join(resourcesDir(), 'frontend');
}

export function userDataDir(): string {
  return app.getPath('userData');
}

export function leagentHome(): string {
  return path.join(userDataDir(), 'leagent');
}

export function runtimeVenvDir(): string {
  if (!IS_PACKAGED) {
    return path.join(backendSourceDir(), '.venv');
  }
  return path.join(userDataDir(), 'runtime', 'venv');
}

export function installedMarkerPath(): string {
  return path.join(userDataDir(), 'runtime', '.installed');
}

export function runtimeVenvPython(): string {
  if (process.platform === 'win32') {
    return path.join(runtimeVenvDir(), 'Scripts', 'python.exe');
  }
  return path.join(runtimeVenvDir(), 'bin', 'python3');
}

export function runtimeVenvBinDir(): string {
  return process.platform === 'win32'
    ? path.join(runtimeVenvDir(), 'Scripts')
    : path.join(runtimeVenvDir(), 'bin');
}

export function ensureDirs(): void {
  const dirs = [
    leagentHome(),
    path.join(userDataDir(), 'runtime'),
    path.join(userDataDir(), 'logs'),
  ];
  for (const d of dirs) {
    fs.mkdirSync(d, { recursive: true });
  }
}
