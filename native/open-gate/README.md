# Open-gate module (appFw.so)

[Method](../../methods/11-open-gate/README.en.md) · [Layout and pins](layout.json) · [Stored record](stored_record.json)

Freestanding AArch64 C linked at fixed addresses into a new section of v0.1.3's `appFw.so`. Other code calls only
[`og.h`](og.h): `og_power_on()` (shooting-screen hook), `og_select(mode)` and `og_selected()` (the menu, PR 2).

## Files

| File | Owns |
| --- | --- |
| `og.c` | The selected mode and `/setting/open_gate.dat` (16 bytes `OGT1`, schema 1, mode, ~mode; `.tmp` + fsync + rename) |
| `og_reconcile.c` | The order of work over the site image: check every site, undo, apply, roll back |
| `og_mem.c` | The four memory targets behind `og_mem_read` / `og_mem_write`, and NTSC/PAL detection |
| `og_entry.S` | The two hook trampolines |
| `og_image.h`, `og_sys.h`, `og_util.c` | Site-image accessors; raw Linux system calls; `memset`/`memcpy` for the compiler |
| `og_sites.S` | `.incbin` of the generated `og_sites.bin` ([format](../../a7m4/open_gate_sites.py)); never committed |

`a7m4/open_gate.py` generates `og_config.h` (camera constants from `layout.json` and `stored_record.json`) and the
linker script, links with the pinned Zig, refuses relocations, undefined symbols and any section but `.text`/`.bss`,
and pins every source here by SHA-256 in `layout.json`.

## Layout in appFw.so

| Piece | VA | File offset | Size |
| --- | --- | --- | --- |
| Code, strings, site image (R-X) | `0x9063000` | `0x5e73000` | 44,572 of 0xc000 bytes |
| State (RW, file-backed zeros) | `0x907f000` | `0x5e7f000` | 1,696 of 0x1000 bytes |
| Program headers | 15 -> 17 entries in place at `0x5e80000`; `e_phnum` and `PT_PHDR` sizes updated | | |
| Hooks | `0x1ddab68`, `0x1e56b2c`: `bl` to the aspect wrappers `0x9012bd8` / `0x9012ce4` -> `bl og_hook_first/second` | | |

Both sections sit in the file's existing zero gap (`0x5e72500..0x5e80000`); the file keeps its length. Each hook
trampoline calls the aspect feature's wrapper first, unchanged (it runs the native presenter creation and registers
the aspect guide), then `og_power_on` with x0-x18 and NZCV preserved.

## Memory targets

As in the kit's helpers (`libJit_level5_*`, `level16`, `level19_ogfile57r300_v1` and `_m1_v4`, the `lcdcycle_v6` cave):

- **CP**: `dlsym(0, ...)` of `_Z9dmm_allocjPj`, `_Z8dmm_freej`, `sen_dma_transfer`; a 4 KB DMM buffer mapped from
  `/dev/mem` with `O_SYNC`; `sen_dma_transfer(0, cp, phys, n)` reads, `(1, phys, cp, n)` writes, whole 64-byte lines.
  Writes re-read their lines just before the write and read them back after. Reads are served from the last 4 KB
  page read.
- **Stored record**: root `0x12b9cc0` -> `+0x20` -> `+0x684` -> count, mode list, records (348 bytes each); the record
  of drive mode `0x8c0` (NTSC) or `0x880` (PAL). The family is the one whose record holds that family's stock or
  open-gate bytes; exactly one must. The list holds all 30 drive modes, so both records are there; on an NTSC camera
  `0x880`'s record holds `e5` at offset `0xb8` where the kit's PAL stock (read on a camera set to PAL) has `98`, so
  only `0x8c0`'s matches (camera trace, diagnostic build `8ba24f9`).
- **av-cam.bin**: `/dev/mem` (no `O_SYNC`) mapped at physical `0x401381000` (file `0x381000..0x3c0000`); each write is
  read back through the mapping and through `pread` of `/dev/mem`.
- **libmpr.so**: `/proc/self/mem` at the start of its offset-0 mapping in `/proc/self/maps` plus the file offset. Data and
  code sites alike (the encoder steps change instructions there): arm64's `/proc/<pid>/mem` write syncs the
  instruction cache of an executable mapping, which the kit's helpers rely on too.

## Reconcile

`og_reconcile(mode)` first reads every site of the family's presets. Each must hold its stock bytes or the new bytes
of one of the presets at that site (the build splits runs so overlapping sites coincide); otherwise `OG_FOREIGN` and
nothing is written. Then presets are undone last-first (sites already as the target wants them are left), and the
target's runs are applied in the kit's order. A failed read or write puts every touched site back to its starting
bytes (`OG_IO`); if that fails too, `OG_UNDO_FAILED`. When memory already matches, nothing is written. `og_power_on`
does nothing with the dial on movie, and nothing at all while the mode is Off and nothing was applied in this process.
