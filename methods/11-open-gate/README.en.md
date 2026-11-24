# Open gate: 3:2 full-sensor video, applied at camera start

[Module](../../native/open-gate/README.md) · [Inputs and layout](../../native/open-gate/layout.json) · [Stored record](../../native/open-gate/stored_record.json)

Builds ArcaneLantern/a7iv-open-gate-test's open-gate state into custom firmware v0.1.3, so it no longer needs a USB
session and a cold boot each time. A native module in `appFw.so` brings camera memory to the mode saved in
`/setting/open_gate.dat` whenever the shooting screen is created, including after a short power-off. Each mode
holds the kit's NTSC and PAL states together:

| Mode | File | Kit steps |
| --- | --- | --- |
| 4K 3:2 | 3840x2560, XAVC HS 4K / XAVC S 4K | `ogsq_v3`, `ogsq880_v1`, `outsz2560_v1`, `ogfile2560_hs_s_v2`, `lcdfill_v2` |
| 5.7K 3:2 | 5760x3840, XAVC HS 4K / XAVC S 4K, 300 Mbps on the 100M settings, I and P pictures only | `og57n_v1`, `og57n880_v1`, `og57cp_v3`, `ogfile57r300m1_v4`, `lcdfill_v2` |

Both encoder steps also set the MP4 headers (track header, sample description, Sony's profile box) to the file's real
size, so editors open it at 3:2 without a remux; Sony's XML in the file still says 3840x2160. Those are libmpr.so
instructions and table entries, changed in memory like the rest. 5.7K is coded without B pictures, which removed the
kit's duplicate frames, and an HEVC recording's edit list starts at frame 0.

Step 1 (`dmmwb4688_v1`, the taller raw write buffer) is written into `nflasha8/DmmCfg.bin` at build time, so it is
always on and the kit's cold-boot rule goes away. The C3 de-squeeze cycle is not included. Off puts every site back
to stock without a power cycle.

The kit's step 2 has an NTSC design for drive mode `0x8c0` (24p/30p) and a PAL design for `0x880` (25p), and its
script asks the user which one the camera is set to. Memory can't answer that: every camera lists every drive mode
(`0x880` at index 9 and `0x8c0` at index 10 of the stored records), each record with its own stock bytes. So both
are applied. Their sites and records don't overlap (none of either design's 6,024 bytes are in the other), and the
mode the camera isn't set to stays idle. A site holding anything but stock or open-gate bytes still stops the apply,
with nothing written.

This layer (PR 1) has no menu yet: the mode comes from `/setting/open_gate.dat` (absent: Off). The menu item (Off /
4K 3:2 / 5.7K 3:2) is PR 2.

## Build

Inputs, all checked against the SHA-256 values in [layout.json](../../native/open-gate/layout.json):

- `BODYDATA.DAT` of A7M4-ToolKit v0.1.3 (custom firmware), not the official 6.02 package;
- the kit's `windows/tools/modding/designs` directory;
- Zig 0.15.2 (official build; the `zig` binary's hash is pinned);
- the published signing keys in `keys/published/` (v0.1.3's updater trusts them).

From the repository root, with Python 3.11+ and `pip install -e ".[firmware,test]"`:

```sh
python -m a7m4.open_gate build --base BODYDATA-custom-v0.1.3.DAT \
    --designs <kit>/windows/tools/modding/designs --zig <zig-0.15.2>/zig \
    --private-key keys/published/A7M4_updater_private.pem \
    --public-key keys/published/A7M4_updater_public.pem --output out/open-gate
```

The output directory must not exist. It gets `BODYDATA.DAT`, `verification.json` (every input and output hash, the
changed members and byte ranges, the module's symbols, the signature check and the package audit) and `work/`.
Only `nflasha8` (`DmmCfg.bin`, 16 bytes), `nflasha15` (`appFw.so`: the module in its zero gap, two program headers,
two hook instructions) and `part_image.sum` change. `av-cam.bin`, `libmpr.so` and `cpapp-b.bin` stay byte-identical:
their open-gate changes are made in memory at run time.

Offline checks: `python -m pytest tests/test_open_gate.py` (site image against the designs and v0.1.3's files; the
camera module's reconcile and record logic on the host against fake memory). Set `OG_DESIGNS` and `OG_V013_DEV` (an
unpacked v0.1.3 `0700_part_image/dev` tree) if they are not at the workspace defaults.

## Limits

- Not yet run on a camera. The memory writes reproduce the kit's own methods and constants, which work on the
  camera, but the module, its start-up trigger and its timing have only been tested offline.
- The planned camera tests of this build are NTSC only. The PAL half is the kit's PAL designs (`ogsq880_v1`,
  `og57n880_v1`), which the kit ran on a camera set to PAL; this build has not been run on one. The kit ran each half
  on its own, never both at once.
- Applied with the dial on stills only, as the kit does; with the dial on movie the next shooting screen retries.
- While a mode is on, record only in the formats and frame rates the kit lists (XAVC HS 4K / XAVC S 4K at 24p NTSC,
  XAVC S 4K at 25p PAL). The menu still shows 100M for 5.7K: the card fills about three times faster.
- Set Proxy Recording to Off, as the kit asks. The camera does not play 5.7K files back.

## Credits and licenses

- Open-gate designs, methods and constants: [ArcaneLantern/a7iv-open-gate-test](https://github.com/ArcaneLantern/a7iv-open-gate-test), GPL-3.0.
- Custom firmware, build tooling and the aspect-ratio hooks this module chains onto:
  [Erlla/sony-a7m4-custom-firmware](https://github.com/Erlla/sony-a7m4-custom-firmware), GPL-3.0.
