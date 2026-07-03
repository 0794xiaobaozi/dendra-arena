# arena architecture

The `dev` branch is migrating the application from a Qt window with embedded business logic to three explicit layers.

## Runtime boundaries

```text
React / TypeScript
  UI, interaction, charts, low-frequency state
        │ Tauri commands + backend-message events
Tauri / Rust
  window lifecycle, backend process ownership, packaging
        │ newline-delimited JSON over stdin/stdout
Python 3.11 backend
  cameras, motion/freeze, recording, experiment clock, stimulation, storage
```

Video frames are an exception to normal React state: backend preview JPEGs are published through `frameBus.ts` and drawn directly to per-camera canvases. Telemetry is stored in Zustand at a lower frequency.

## Command envelope

```json
{"id":"uuid","type":"start_preview","payload":{"cameras":[]}}
```

Every command produces exactly one response:

```json
{"kind":"response","id":"uuid","ok":true,"result":{}}
```

Unsolicited runtime updates use events:

```json
{"kind":"event","type":"camera_telemetry","payload":{}}
```

The protocol is versioned by the initial `backend_ready` event. JSON is written one object per line; stdout is reserved for protocol traffic.

## State ownership

- Setup owns mutable camera assignment, ROI, freeze strategy, shock schedule and output configuration.
- Run renders an immutable configuration snapshot and accepts only safe runtime actions.
- Review reads completed artifacts and never mutates the recorded session.
- Python is authoritative for clocks, recording state, behavior state and hardware errors.
- React is authoritative only for selection and presentation state such as `selectedBoxId` and `motionBoxId`.

## Resource lifecycle

`CameraRuntime` owns one Python thread. Capture, video writing, and release all happen on that same thread. Stop requests use a `threading.Event`; the coordinator joins every runtime before finalizing the manifest. Manifests are written through a temporary file and atomically replaced.

## Migration rule

The existing PySide6 code remains in `src/` until equivalent backend behavior is covered by tests. New UI code must not import it. Hardware algorithms may be adapted behind backend interfaces and removed from the legacy tree only after parity checks.
