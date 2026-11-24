# Open Gate state fixes 1 — experimental release

Release tag: `v0.1.3-open-gate-state-fixes.1`. Assessment date: November 24, 2026.

## Package identity and source

- Target: **Sony ILCE-7M4 (a7 IV), initially on official Sony firmware 6.02**.
- Upstream fork: [leogenot/sony-a7m4-custom-firmware-open-gate](https://github.com/leogenot/sony-a7m4-custom-firmware-open-gate),
  commit `2b96e29b78954945459faeca17b99bc69315afce`.
- Firmware implementation: `1747e460a3e6a51b64a6d2a0b7c71666d1d56ec5`. Later release-tag changes document testing and
  add a host memory-management wrapper; the verified native source hashes remain unchanged.
- Arcane Lantern design snapshot: `2f2a02190808797a01b31a27d5eb17cfea3d4820`.
- Base: Erlla v0.1.3 `BODYDATA.DAT`, SHA-256 `cfb7929594f3f0a770b9fbecaff1269cd945bc0932e3ddbabf73050f8eda475f`.
- Release `BODYDATA.DAT`: **757,480,856 bytes**, SHA-256
  **`6b303b050e12d0bb19af3a406ee6820ce90c0be5f2f3307249d42da0ce44c536`**.
- AArch64 module text: 46,572 bytes, SHA-256 `0056c3258b6d3b35e94590eea02d5fd22a2d9f958e10eec93130b4dbb5ab364e`.

Download from this fork's [release](https://github.com/Sloopdog/sony-a7m4-custom-firmware-open-gate/releases/tag/v0.1.3-open-gate-state-fixes.1).
Use `shasum -a 256 BODYDATA.DAT` on macOS and compare the complete digest. A valid signature uses a deliberately
public experimental key; it does not authenticate the publisher. Existing source licenses and third-party rights remain in force.

## Changes from the upstream fork

The saved request and verified active mode are separate. New processes report unverified state until reconciliation
succeeds. A failed mode operation latches **Reset in stills**, preventing further patch attempts in that process.
The mode choice is saved and synced before live memory writes; failed apply operations attempt to restore the previous
saved choice. The menu still requires stills mode. See [implementation details](../../native/open-gate/LOCAL-FIXES.md).

There is no added record-button lock, fault popup or C3 de-squeeze cycle. The custom sound menus remain replaced by
Open Gate. Off restores runtime sites, not the whole firmware installation.

## Offline and package validation

- **63 targeted tests passed**, no failures or skips, with the exact pinned inputs.
- Native host tests used AddressSanitizer and UndefinedBehaviorSanitizer; AArch64 compilation used pinned Zig 0.15.2.
- Composed ELF, menu layout/relocations and all 68 string banks checked; original Sony strings preserved.
- Signed package, DEND/header/image CRCs, backup templates and **739,727 encrypted-frame checks** passed the package
  verifier. Final decoding matched the constructed plaintext byte for byte.
- Relative to the Erlla base, changed package members are `nflasha15`, `nflasha8` and `part_image.sum`.
- A separate host-only wrapper collected ExtFS reference cycles between replacements to reduce retained memory.

These checks are distinct from hardware testing. Numerical release evidence is in
[state-fixes-1-validation.json](state-fixes-1-validation.json), also attached as `VALIDATION.json` to the release.

## Observed installation and recording

One ILCE-7M4 was checked on official 6.02. Settings were backed up with both BK4 checksums verified. ZM4 1.0.3 on an
Apple Silicon Mac completed all six installer stages, including a 766-block updater backup and a single updater-patch
commit with independent readback. The operator reported that the on-camera update finished and the camera restarted.
The subsequent USB check confirmed normal MSC operation, and the Open Gate menu was visible.

Two new **NTSC XAVC S 5.7K 3:2** recordings were then examined:

| Check | Clip A | Clip B |
| --- | --- | --- |
| Duration | 6.5065 s | 10.0100 s |
| Decoded dimensions | 5760 × 3840 | 5760 × 3840 |
| Frame rate | 24000/1001 | 24000/1001 |
| Decoded frames | 156 | 240 |
| Picture types | 13 I / 143 P | 20 I / 220 P |
| Video bitrate | 301.48 Mbps | 299.44 Mbps |
| Pixel format | 10-bit 4:2:2 | 10-bit 4:2:2 |
| Audio | 48 kHz stereo PCM16 | 48 kHz stereo PCM16 |
| Audio samples per channel | 312,312 | 480,480 |
| Sony colour tags | Rec.709 | S-Log3 / S-Gamut3.Cine |

Both complete video/audio streams decoded without errors. All 396 video frames had unique decoded hashes, continuous
timestamps and dimensions matching the MP4 headers. No visible padding or corruption appeared in first/middle/last
frame samples. Sony XML retained 3840 × 2160/100M labels. Both audio tracks were approximately −77 dBFS RMS; the
operator described a very quiet scene. This verifies audio stream integrity, not useful microphone level or perceptual sync.

## Not established by this test

4K on this installed build, PAL, HEVC, long-take/thermal stability, HDMI edge coverage, restart/sleep/wake persistence,
fault injection on hardware, failure rollback and interrupted-flash recovery remain unverified. LUT import and the
other inherited custom-firmware features were not exercised. No complete continuous visual playback or listening test
was performed. Earlier temporary-kit 4K/5.7K results are not counted as tests of this installed build.

Personal settings, calibration, camera identifiers, raw service logs and test photographs/videos are excluded from
the public release. Backups are not a guarantee of recovery from a failed firmware flash.

Credits: Arcane Lantern for the temporary open-gate designs, Erlla and contributors for the underlying custom firmware,
leogenot for the integrated Open Gate menu, and Hippasu for ZM4. Preserve [third-party notices](../../THIRD_PARTY_NOTICES.md).
