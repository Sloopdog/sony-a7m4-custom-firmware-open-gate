# Open gate: 3:2 full-sensor video, applied at camera start

[Module](../../native/open-gate/README.md) · [Inputs and layout](../../native/open-gate/layout.json) · [Stored record](../../native/open-gate/stored_record.json)

Builds ArcaneLantern/a7iv-open-gate-test's open-gate state into custom firmware v0.1.3, so it no longer needs a USB
session and a cold boot each time. A native module in `appFw.so` brings camera memory to the mode saved in
`/setting/open_gate.dat` whenever the shooting screen is created, including after a short power-off. The modes are
the kit's two states, NTSC and PAL:

| Mode | File | Kit steps |
| --- | --- | --- |
| 4K 3:2 | 3840x2560, XAVC HS 4K / XAVC S 4K | `ogsq_v3` (PAL `ogsq880_v1`), `outsz2560_v1`, `ogfile2560_hs_s_v2`, `lcdfill_v2` |
| 5.7K 3:2 | 5760x3840, XAVC HS 4K / XAVC S 4K, 300 Mbps on the 100M settings, I and P pictures only | `og57n_v1` (PAL `og57n880_v1`), `og57cp_v3`, `ogfile57r300m1_v4`, `lcdfill_v2` |

Both encoder steps also set the MP4 headers (track header, sample description, Sony's profile box) to the file's real
size, so editors open it at 3:2 without a remux; Sony's XML in the file still says 3840x2160. Those are libmpr.so
instructions and table entries, changed in memory like the rest. 5.7K is coded without B pictures, which removed the
kit's duplicate frames, and an HEVC recording's edit list starts at frame 0.

Step 1 (`dmmwb4688_v1`, the taller raw write buffer) is written into `nflasha8/DmmCfg.bin` at build time, so it is
always on and the kit's cold-boot rule goes away. The C3 de-squeeze cycle is not included. Off puts every site back
to stock without a power cycle. The camera's NTSC/PAL setting is detected on the camera from its stored drive-parameter
record; a camera matching neither is left untouched.

## Menu item

"Open Gate", with three options: **Off**, **4K 3:2** and **5.7K 3:2**.

- **Where:** MENU > Shooting > Media, after Display Media Info. It is not next to File Format: Image Quality/Rec
  already holds all 30 of its fixed slots (the menu tree is fixed arrays of 30 entries per group), and Media is the
  group right after it. The item is appended there the way the custom firmware's LUT and custom-sound items are
  appended to theirs; no native item moves.
- **Applies on confirm**, through the same reconcile as at start: every site is checked, the chosen preset is
  written and read back, and Off puts every site back to stock without a power cycle. The choice is saved in
  `/setting/open_gate.dat` and re-applied at the next shooting screen.
- **Stills only:** the item is greyed while the dial is on movie.
- **On failure** (another apply running, coprocessor not ready, foreign bytes, an I/O error, or the record could not
  be saved) nothing is shown: the native apply method ignores the commit's result (`appFw.so` 0x1c15620), so there
  is no error path to use. The item keeps showing the mode that is really in place (`og_selected()`). If the bytes
  were applied but the record could not be saved, the item shows the new mode, and the next power-on goes back to
  the saved one.

The labels are in all 68 horizontal and vertical string banks, in English in every language (Off is Sony's own,
translated, string). The banks cannot grow, so four of the custom firmware's own custom-sound texts were shortened
to make room (three in the Chinese banks):

| Id | Before | After |
| --- | --- | --- |
| `0x0200ab61` | Use this audio for electronic shutter? | Use as shutter sound? |
| `0x0200ab62` | Use this audio for focus? | Use as focus sound? |
| `0x0200ab63` | Restore default focus sound? | Reset focus sound? |
| `0x0200ab5e` | Import from SD | Import |
| `0x0200ab61` (Simplified Chinese) | 是否将此音频用于电子快门声？ | 用作快门声？ |
| `0x0200ab62` (Simplified Chinese) | 是否将此音频用于对焦声音？ | 用作对焦声音？ |
| `0x0200ab63` (Simplified Chinese) | 是否恢复默认对焦声音？ | 恢复默认对焦声音？ |
| `0x0200ab61` (Traditional Chinese) | 是否將此音訊用於電子快門聲？ | 用作快門聲？ |
| `0x0200ab62` (Traditional Chinese) | 是否將此音訊用於對焦聲音？ | 用作對焦聲音？ |
| `0x0200ab63` (Traditional Chinese) | 是否恢復預設對焦聲音？ | 恢復預設對焦聲音？ |

The shutter sound is shared by every shutter type in this firmware, so "shutter sound" is still exact. No Sony string
changes. The module's [README](../../native/open-gate/README.md) has the registries, hooks and record layouts.

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
nine hook instructions, the Media group's count and new entry, one relocation after `.rela.dyn` and the two fields
that size it; and the 68 string banks, same sizes) and `part_image.sum` change. `av-cam.bin`, `libmpr.so`
and `cpapp-b.bin` stay byte-identical: their open-gate changes are made in memory at run time.

Offline checks: `python -m pytest tests/test_open_gate.py`: the site image against the designs and v0.1.3's files;
`og_reconcile.c` and `og.c` on the host against fake memory, and `og_mem.c` against fake DMA, `/dev/mem` and
`/proc/self/maps`; `og_menu.c` against a fake `og.h` and native maps, with its records compared to v0.1.3's; the
composed `appFw.so` (linked with the pinned Zig) and all 68 edited banks, decoded. Set `OG_DESIGNS`, `OG_V013_DEV`
(an unpacked v0.1.3 `0700_part_image/dev` tree), `OG_602_DEV` (the same for stock 6.02) and `OG_ZIG` if they are
not at the workspace defaults.

## Limits

- Not yet run on a camera. The memory writes reproduce the kit's own methods and constants, which work on the
  camera, but the module, its start-up trigger and its timing have only been tested offline.
- The planned camera tests of this build are NTSC only. The PAL presets are the kit's PAL designs (`ogsq880_v1`,
  `og57n880_v1`), which the kit ran on a camera set to PAL; this build has not been run on one.
- Applied with the dial on stills only, as the kit does; with the dial on movie the next shooting screen retries,
  and the menu item is greyed.
- The menu item has not been run on a camera either (check C8): the records copy custom sounds' Volume item, which
  works on the camera, with the fields listed in `og_menu.c` changed.
- While a mode is on, record only in the formats and frame rates the kit lists (XAVC HS 4K / XAVC S 4K at 24p NTSC,
  XAVC S 4K at 25p PAL). The menu still shows 100M for 5.7K: the card fills about three times faster.
- Set Proxy Recording to Off, as the kit asks. The camera does not play 5.7K files back.

## Credits and licenses

- Open-gate designs, methods and constants: [ArcaneLantern/a7iv-open-gate-test](https://github.com/ArcaneLantern/a7iv-open-gate-test), GPL-3.0.
- Custom firmware, build tooling and the aspect-ratio hooks this module chains onto:
  [Erlla/sony-a7m4-custom-firmware](https://github.com/Erlla/sony-a7m4-custom-firmware), GPL-3.0.
