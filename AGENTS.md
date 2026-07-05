# AGENTS.md

## Architecture

| Layer | Location | Role |
|-------|----------|------|
| **Frontend** (React/TypeScript) | `frontend/` | UI, interaction, charts, low-freq state |
| **Shell** (Tauri/Rust) | `src-tauri/` | Window lifecycle, backend process ownership, packaging |
| **Backend** (Python 3.11) | `backend/arena_backend/` | Cameras, motion/freeze, recording, experiment clock, stimulation |

`src/` and `main.py` are **deprecated PySide6 legacy** — do not import from them. They will be removed once 1.0 ships.

## Dev commands

```powershell
npm install
npm run dev              # Vite dev server at :1420 with mock telemetry
npm run tauri dev         # Tauri window + Vite + real Python backend
npm run check             # tsc build + UI smoke test (Playwright, needs Edge/Chromium)
npm run test:ui           # UI smoke test only
npm run build             # tsc + Vite production build → frontend/dist/
```

### Python backend tests

```powershell
$env:PYTHONPATH="backend"
pixi run python -m pytest backend/tests -q
```

`PYTHONPATH="backend"` is **required** — the backend package is not installed globally.

## Key conventions

### Python backend protocol

Tauri spawns `python -m arena_backend.main`, communicating via newline-delimited JSON over stdin/stdout. Every command receives a single response:

```json
{"id":"uuid","type":"command_name","payload":{}}   → request
{"kind":"response","id":"uuid","ok":true,"result":{}}  → reply
{"kind":"event","type":"backend_ready","payload":{...}} → unsolicited event
```

`stdout` is reserved for protocol traffic. `stderr` goes to Tauri's log. Video frames are **not** routed through React state — they're drawn to canvases via `frameBus.ts`.

### Submodule required

`RpiBeh_repo` (submodule, `git clone --recurse-submodules`) is required for freeze detection. Tauri bundles `RpiBeh_repo/client_host/` as a resource.

### Environment

- Python 3.11 managed by Pixi (not pip/venv at project level)
- TypeScript strict mode (`frontend/tsconfig.json`)
- Vite dev server on `:1420` (strict port)
- Tauri window: fixed 1440×1000, no decorations, not resizable

### Stimulator safety

Protocols with shock events require explicit stimulator detection and arming before experiments can run. Config is locked during active experiments.

## References

- Architecture details: `docs/ARCHITECTURE.md`
- Protocol format: `protocols/README.md`