<p align="center">
  <img src="docs/assets/logo.svg" alt="LeAgent Logo" width="120" height="120">
</p>

<h1 align="center">LeAgent</h1>

<p align="center">
  <strong>Local-first intelligent office automation — conversational AI, visual workflows, and 100+ tools in one deployable stack.</strong>
</p>

<p align="center">
  <a href="../../actions/workflows/ci.yml"><img src="../../actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="../../releases/latest"><img src="https://img.shields.io/github/v/release/vixues/LeAgent?display_name=tag&sort=semver&color=blue" alt="Latest Release"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776ab.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/React-19-61dafb.svg" alt="React 19">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-green.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen.svg" alt="PRs Welcome">
</p>

<p align="center">
  <a href="README.md">中文文档</a>
</p>

<p align="center">
  <img src="docs/assets/screenshots/hero.jpg" alt="LeAgent Screenshot" width="720">
</p>

---

**LeAgent** is a self-hostable platform for building LLM-powered automation: chat assistants, drag-and-drop workflows, declarative rules, skills, and integrations — without stitching together separate products.

- **Agent runtime** — multi-turn sessions with streaming, tool execution, tiered model routing, layered prompts, and cognitive memory
- **100+ tools** — documents, web, data, code execution, databases, generative UI, coding projects, and more
- **Visual workflows** — ReactFlow editor with YAML export, templates, and every tool as a typed node
- **Multi-provider LLM** — OpenAI, Anthropic, DeepSeek, DashScope, Azure OpenAI, Ollama, vLLM
- **Zero-config default** — SQLite out of the box, single Docker container, optional PostgreSQL / Milvus

---

## Quick Start

### Local dev (recommended for hackers)

**Prerequisites:** git, [uv](https://docs.astral.sh/uv/), Node.js 20+ or 22+

```bash
git clone https://github.com/vixues/LeAgent.git
cd LeAgent
./start.sh                # backend :7860 + frontend :5173
```

### Docker

```bash
cd LeAgent/deploy
cp .env.example .env      # set LEAGENT_SECRET_KEY + provider keys
docker compose up -d --build
```

API at `http://localhost:8000/docs`.

### Manual setup

```bash
# Backend
cd backend
uv sync --extra dev
uv run leagent init
uv run leagent app

# Frontend (separate terminal)
cd frontend
npm install && npm run dev
```

### One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/vixues/LeAgent/main/scripts/install.sh | bash
```

### Desktop app (Beta)

Pre-built installers for each platform are attached to every GitHub release — just download and run. No Python, Node, or Docker required.

| Platform | Download | Notes |
|---|---|---|
| **Windows 10/11 (x64)** | [`LeAgent-Setup-*.exe`](../../releases/latest) | NSIS installer; desktop + start-menu shortcut |
| **macOS (Apple Silicon)** | [`LeAgent-*-arm64.dmg`](../../releases/latest) | Unsigned — `xattr -dr com.apple.quarantine /Applications/LeAgent.app` after install |
| **macOS (Intel)** | [`LeAgent-*.dmg`](../../releases/latest) | Same Gatekeeper note as above |
| **Linux (x64)** | [`LeAgent-*.AppImage`](../../releases/latest) / [`LeAgent-*.deb`](../../releases/latest) | AppImage: `chmod +x` then run. `.deb`: `sudo dpkg -i` |

The desktop build bundles its own Python runtime + backend payload, so the only thing on disk is the LeAgent app itself.

See all releases: **<https://github.com/vixues/LeAgent/releases>**

---

## Contributing

Issues and pull requests are welcome. Please:

1. Open an issue for larger changes or ambiguous scope.
2. Run tests (`cd backend && uv run pytest tests/ -v` / `cd frontend && npm run test`) for touched areas.
3. Follow [`AGENTS.md`](AGENTS.md) for coding conventions and i18n rules.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full guidelines.

---

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
