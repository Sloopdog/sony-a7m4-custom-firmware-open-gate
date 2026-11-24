# Open-gate state and persistence fixes

Based on `2b96e29b78954945459faeca17b99bc69315afce`; firmware implementation commit `1747e460a3e6a51b64a6d2a0b7c71666d1d56ec5`.
Installed on one ILCE-7M4, with two short NTSC 5.7K recordings verified. Hardware fault cases and broader operating
conditions remain untested. See the [dated validation scope](../../docs/releases/state-fixes-1.md).

Current development source also integrates Arcane Lantern `lcdcycle_v7`: raw C3 presses in movie mode cycle the rear
LCD through 3:2, 2:1, 2.25:1 and 2.4:1 while keeping focus frames. The original cave overlaps v0.1.3, so the pinned blob
is instruction-relocated to the tail of this module's RX segment and its stock C3 hook is redirected there. Tests pin
the design, source and relocated hashes, the displaced instruction, return target, hook and final module bytes. This
addition is offline-tested only and is outside the installed `state-fixes.1` validation scope.

## Behavior

- The saved request and verified live mode are separate. A new process starts unverified. Starting in movie does not apply patches or falsely report the saved mode as active. Start in stills, then check the mode before recording.
- The menu's fourth row, **Reset in stills**, represents unverified or failed state. It is not a recording format; selecting it writes nothing. It reuses the fourth existing sound-option alias, and its text fits all 68 resource banks.
- Failed menu operations and startup write/validation failures latch until a cold process restart. Neither subsequent screen hooks nor another mode selection can resume patch writes. Startup NOT_READY/BUSY can retry, since those statuses occur before writes.
- The requested choice must be saved and synced before any live-mode change. If storage fails, the live mode stays unchanged and the menu reports the reset status. A failed apply also attempts to restore the previous saved choice. Failure to restore settings remains visible; a failed memory rollback retains its more serious status.
- Record loading is serialized with writes. Menu getters no longer read settings concurrently with an update.

The fault indication does **not** disable Sony's record button or show a popup. After an error, stop recording, power off, remove the battery for 10 seconds, and restart in stills. If the status persists, stop testing. A storage failure after rename may leave either saved choice durable; the code explicitly declines to report success in that case.

Off restores runtime patch sites only. The custom firmware, hooks, and larger on-disk raw buffer remain installed.

## Offline validation

`tests/test_open_gate.py` covers mode transitions in NTSC/PAL, movie startup, unavailable startup memory, successful and failed rollback, settings-open failures, sync failures before and after rename, failed settings rollback, error-state persistence across callbacks, and cold-process recovery. The native host programs use AddressSanitizer and UndefinedBehaviorSanitizer.

With the exact Erlla v0.1.3 inputs and pinned Zig available, the same suite also cross-compiles the AArch64 module,
relocates and pins the C3 cycle, checks the composed ELF, option/parent maps and relocation changes, and verifies all
68 string banks preserve Sony's original strings. Menu records occupy initialized RW padding at `0x907fc00`, outside
the zero-initialized runtime state; composition checks that they do not overlap.

To run, provide `OG_DESIGNS`, `OG_V013_DEV`, `OG_602_DEV`, and `OG_ZIG`, then run:

```sh
python -m pytest tests/test_open_gate.py
```

The container verifier test additionally uses `A7M4_V013_DAT`. These tests do not call USB or camera tools. They do not prove the timing of Sony's startup hooks, recording-button behavior under faults, sleep/wake operation, or recovery after an interrupted flash. The separately built package and limited recording tests are documented in the linked validation scope.
