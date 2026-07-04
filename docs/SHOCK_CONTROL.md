# arena stimulator backend

The standalone scripts from `C:\Users\eaad0\Desktop\shock_control` were normalized into
`backend/arena_backend/stimulator.py`. The arena backend is now the sole owner of USB access;
React never imports PyUSB or writes device packets directly.

## Preserved device protocol

- USB VID/PID: `10C4:EA61`
- OUT endpoint: `0x02`
- IN endpoint: `0x82`
- Reset packet: `f0000000000000000000000000`
- Current encoding: `0.01 mA` little-endian integer
- Duration encoding: unsigned 16-bit device protocol units

The byte-level packet format has regression tests in `backend/tests/test_setup_backend.py`.

## Safety model

The controller is fail-closed:

1. USB connection alone does not arm the device.
2. Arming requires an explicit confirmation payload.
3. Test pulses require a second explicit confirmation.
4. The controller automatically disarms after an experiment or test flow.
5. UI seconds are not converted to device duration units without calibration.

The original scripts explicitly warned that their `duration` integer was not proven to equal
seconds. arena preserves that distinction. Configure a verified conversion only after physical
calibration:

```powershell
$env:ARENA_SHOCK_DURATION_UNITS_PER_SECOND="10"
npm run tauri dev
```

The value above is an example, not a calibration recommendation. Without this environment
variable, Preflight blocks shock-enabled sessions and real pulse commands fail.

## Backend commands

- `get_stimulator_status`
- `connect_stimulator`
- `arm_stimulator`
- `disarm_stimulator`
- `stimulator_test`

Experiment scheduling uses the same `StimulatorController`. A shock event is emitted as
`triggered`, `failed`, or `skipped_unarmed`, with the hardware error included when applicable.
