# Open-gate module (appFw.so)

[Method](../../methods/11-open-gate/README.en.md) · [Layout and pins](layout.json) · [Stored record](stored_record.json)

Freestanding AArch64 C linked at fixed addresses into a new section of v0.1.3's `appFw.so`. Other code calls only
[`og.h`](og.h): `og_power_on()` (shooting-screen hook), `og_select(mode)` and `og_selected()` (the menu item,
[`og_menu.h`](og_menu.h)).

## Files

| File | Owns |
| --- | --- |
| `og.c` | The selected mode and `/setting/open_gate.dat` (16 bytes `OGT1`, schema 1, mode, ~mode; `.tmp` + fsync + rename) |
| `og_reconcile.c` | The order of work over the site image: check every site, undo, apply, roll back |
| `og_mem.c` | The four memory targets behind `og_mem_read` / `og_mem_write`, and NTSC/PAL detection |
| `og_entry.S` | The two hook trampolines |
| `og_menu.c` | The Open Gate menu item: getter, setter, commit, blocked, and its records in six native maps |
| `og_menu_entry.S` | The three registrar trampolines and four per-mid filters |
| `og_image.h`, `og_sys.h`, `og_util.c` | Site-image accessors; raw Linux system calls; `memset`/`memcpy` for the compiler |
| `og_sites.S` | `.incbin` of the generated `og_sites.bin` ([format](../../a7m4/open_gate_sites.py)); never committed |

`a7m4/open_gate.py` generates `og_config.h` (camera constants from `layout.json` and `stored_record.json`) and the
linker script, links with the pinned Zig, refuses relocations, undefined symbols and any section but `.text`/`.bss`,
and pins every source here by SHA-256 in `layout.json`.

## Layout in appFw.so

| Piece | VA | File offset | Size |
| --- | --- | --- | --- |
| Code, strings, site image (R-X) | `0x9063000` | `0x5e73000` | 46,148 of 0xc000 bytes |
| State and menu records (RW, file-backed zeros) | `0x907f000` | `0x5e7f000` | 2,416 of 0x1000 bytes |
| Program headers | 15 -> 17 entries in place at `0x5e80000`; `e_phnum` and `PT_PHDR` sizes updated | | |
| Hooks | `0x1ddab68`, `0x1e56b2c`: `bl` to the aspect wrappers `0x9012bd8` / `0x9012ce4` -> `bl og_hook_first/second` | | |
| Menu hooks | seven more, below | | |

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
  open-gate bytes; exactly one must.
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

## Menu item

One custom leaf, mid 1600, options 5638-5640 (Off / 4K 3:2 / 5.7K 3:2, raw values 0-2 = `og_mode`). Its records are
custom sounds' Volume item's (v0.1.3: leaf `0x8ff80a0`, row `0x8ff8160`, profile `0x8ff8660`) with the fields listed
in [`og_menu.c`](og_menu.c) changed; they are copied into `.bss` and given their pointers when the registrars run.

| Native map (object, registrar) | Entries | Inserted by |
| --- | --- | --- |
| leaf `0x7614238`, `0x1cd0d90` | 1600 -> leaf descriptor (0xc0) | `og_menu_register_options` |
| option `0x7614148`, `0x1cd0fe4` | 5638-5640 -> option rows (0x80 each) | `og_menu_register_options` |
| profile `0x7614178`, `0x1cd1238` | 1600 -> profile (0x80) | `og_menu_register_parent` |
| parent `0x7614208`, `0x1cd1934` | 5638-5640 -> 1600 | `og_menu_register_parent` |
| value `0x76142f8`, `0x1cd29f8` | 5638-5640 -> themselves | `og_menu_register_alias` |
| alias `0x7614328`, `0x1cd2bec` | 5638-5640 -> themselves | `og_menu_register_alias` |

Each map is a static object; `compose_ap` checks the GOT slot each constructor loads it from is an
`R_AARCH64_RELATIVE` to that address. The leaf, profile and value maps are built earlier in the same constructor
functions as the hooked option (`0x1732000`), parent (`0x173210c`) and alias (`0x1737974`) calls, so those three
hooks insert into them too.

| Hook | Was (v0.1.3) | Now | Handles |
| --- | --- | --- | --- |
| `0x1732000` | `bl 0x90108b8` (aspect) | `bl og_menu_hook_options` | previous, then leaf and option rows |
| `0x173210c` | `bl 0x90108e0` (aspect) | `bl og_menu_hook_parent` | previous, then profile and parent |
| `0x1737974` | `bl 0x9010908` (aspect) | `bl og_menu_hook_alias` | previous, then value and alias pairs |
| `0x1c08bc0` support (mid in w1) | `b 0x8fb90c8` (Volume) | `b og_menu_supported` | 1 for mid 1600 |
| `0x1c1116c` id map (mid in w1) | `b 0x8fb90e0` (Volume) | `b og_menu_mapped` | 1600 -> 1600 |
| `0x1c155e0` apply (leaf in x20) | `b 0x8fb90f8` (Volume) | `b og_menu_apply` | our leaf skips the parameter broker, to `0x1c15604` |
| `0x1c14e6c` blocked (mid in w0) | `b 0x8fb877c` (Volume) | `b og_menu_blocked` | 1 for mid 1600 in movie |

Every other mid, leaf and alias goes to the previous head unchanged, which ends in the stock code. The native apply
method calls the getter (which returns the value the setter staged while browsing) to find the confirmed row, then
the commit with its alias, and ignores the commit's result; a failed `og_select` drops the staged value, so the item
shows `og_selected()` again. Labels: `0x0200ab51`-`0x0200ab53` in the 68 banks and Sony's Off `0x0200a00f`
([method](../../methods/11-open-gate/README.en.md#menu-item)). Not yet placed in a menu group: see the method.
