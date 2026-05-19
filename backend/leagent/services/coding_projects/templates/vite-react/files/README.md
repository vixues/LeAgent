# Vite + React + TypeScript scaffold

The LeAgent supervisor runs `npm install` once (cached behind a
marker file under `node_modules/`), then `npm run dev` with a fixed
port and host. Hot-module replacement works through the signed
WebSocket reverse-proxy.

## Local commands

```bash
npm install
npm run dev
npm run build
```

Edit `src/App.tsx` and save — Vite reloads automatically.
