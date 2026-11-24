# C3 de-squeeze development build

This source revision integrates Arcane Lantern's pinned `lcdcycle_v7` rear-screen preview cycle with the Open Gate
state fixes. It is a development build. It has not been installed on a camera and is not the firmware validated in
[`state-fixes-1.md`](state-fixes-1.md).

## Behavior

In movie mode, a raw C3 press cycles:

1. 3:2
2. 2:1, intended for 1.33× anamorphic preview
3. 2.25:1, intended for 1.5× preview
4. 2.4:1, intended for 1.6× preview
5. back to 3:2

The cycle preserves focus frames. It changes the rear LCD preview only; it does not alter the recorded frame or HDMI
output. Because it intercepts the raw C3 event in movie mode, the camera action normally assigned to C3 may not run
there while this hook is active.

## Integration

The Arcane Lantern cave at `0x50bba60` is not free in Erlla v0.1.3. The build therefore verifies the exact source
design and blob, relocates supported AArch64 PC-relative branches and addresses, and places the 1,440-byte result at
`0x906ea60`, the tail of the Open Gate RX segment. The destination keeps the source page offset so the blob's
ADRP-plus-ADD data references remain valid. The stock C3 handler instruction at `0x1f06594` is replaced with a branch
to the relocated entry; the blob executes the displaced instruction and returns to `0x1f06598`.

Pinned identities are in [`native/open-gate/layout.json`](../../native/open-gate/layout.json). Offline tests require
the design, source blob, relocated blob, combined module, stock hook bytes and composed branch to match exactly. A
successful package build still establishes only static composition and container integrity. Camera startup, C3 event
timing, focus-frame behavior, sleep/wake and HDMI behavior require a separate hardware test before release.

## Offline result, November 24, 2026

- `tests/test_open_gate.py`: 63 passed, 1 skipped. The skip is the existing comparison requiring an unpacked official
  6.02 tree; the v0.1.3 composition, C3 relocation and hook checks ran.
- `BODYDATA.DAT`: 757,480,856 bytes; SHA-256
  `13f85fa7d057942d97b2ab83ff473437f12ad34aedd5ea9bf7256140a0e12347`.
- Combined RX module: 49,152 bytes; SHA-256
  `18a8e2c0c0d25d12a7314055d3a537167ff3af52e51a863e0fe5ab132d220be1`.
- Package verifier: 739,727 blocks and the reconstructed plaintext compared byte for byte; RSA signature, DEND CRC,
  header CRC and all image CRCs passed.
- `camera_tested`, `hardware_acceptance` and `camera_io` are false in the verification record.

The offline package is retained outside source history. Do not replace or relabel the camera-tested
`v0.1.3-open-gate-state-fixes.1` release with it.
