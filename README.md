# arena

> Neuroscience experiment cockpit — multi-camera video recording, real-time freeze detection, and programmable shock stimulation.

**Three-layer architecture**: React (TypeScript) frontend → Tauri (Rust) desktop shell → Python 3.11 backend.

## Quick start

```powershell
git clone --recurse-submodules https://github.com/0794xiaobaozi/dendra-arena.git
cd dendra-arena
```

### Development

```powershell
npm install
npm run dev              # browser preview with mock data
npm run tauri dev         # full desktop app with Python backend
npm run check             # typecheck + build + UI smoke test
```

Backend tests:

```powershell
$env:PYTHONPATH="backend"
pixi run python -m pytest backend/tests -q
```

### Build installer

```powershell
.\scripts\build-backend.ps1   # package Python backend via PyInstaller
npm run tauri build             # produce MSI/NSIS installer
```

Or push a `v*` tag — GitHub Actions builds and publishes the release.

## Requirements

- [Pixi](https://pixi.sh) for Python 3.11 environment
- Rust toolchain (`rustup toolchain install stable`)
- Node.js 22+

## Architecture

| Layer | Location | Role |
|-------|----------|------|
| Frontend | `frontend/` | UI, charts, low-frequency state |
| Shell | `src-tauri/` | Window lifecycle, backend process ownership |
| Backend | `backend/arena_backend/` | Cameras, freeze detection, recording, stimulation |

`src/` and `main.py` are deprecated PySide6 legacy.

Backend communicates via newline-delimited JSON over stdin/stdout. Video frames are drawn to canvases directly — not routed through React state. See `docs/ARCHITECTURE.md`.
