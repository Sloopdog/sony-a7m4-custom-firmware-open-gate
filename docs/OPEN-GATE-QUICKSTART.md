# Using this open-gate build

Read the [installation instructions and risks](../README.md#install) and [test scope](releases/state-fixes-1.md)
before using the experimental firmware. These steps apply after installation; they are not the temporary USB kit.

## Select a recording mode

1. Disconnect USB. Set the lower **Still/Movie/S&Q selector to the still-camera icon**; the upper P/A/S/M dial controls
   exposure, not the still/movie selection. If needed, press the lower selector's front lock-release button.
2. Open **MENU → Shooting → Media → Open Gate → Mode**. Select **4K 3:2** first and confirm.
3. Recheck the setting. Proceed only when it reports the intended mode. **Reset in stills** means unverified state or
   a failed operation; it is not a shooting format.
4. Switch to movie. Use full-frame **XAVC S 4K, 24p, 100M 4:2:2 10bit** on NTSC, or XAVC S 4K at 25p on PAL.
   Turn **Proxy Recording Off**. Record a short moving scene with speech or a clap, and verify the saved file.
5. After 4K is established, return to stills to choose **5.7K 3:2**. The 100M menu selection records about 300 Mbps in
   this mode; use a suitable fast card (upstream specifies SD V60/V90 or CFexpress Type A).

Starting in movie does not apply a saved patch. Start in stills and check the selected mode on each cold start.
"This function is currently disabled" in movie is the mode-selection guard; switch to stills before changing it.
If it remains disabled in stills, or **Reset in stills** appears, stop testing, power off, remove the battery for
10 seconds, restart in stills, and inspect once. If the issue persists, stop and investigate; do not repeatedly apply.
This recovery instruction applies during operation, **never during an active firmware flash**.

The reset status does not lock Sony's record button or display a new popup. **Off** restores runtime patch sites;
it does not uninstall the custom firmware or the larger stored raw buffer.

## Anamorphic preview and C3

**This firmware does not include the temporary Arcane Lantern kit's C3 de-squeeze cycle.** Assigning C3 cannot enable
that missing feature. Use your external monitor's anamorphic/de-squeeze setting at the factor specified by the lens
(for example, 1.33×, 1.5×, 1.8× or 2× if supported by the monitor), then apply that lens factor in post-production.
This is preview configuration; it does not change the recorded file's 3:2 pixel dimensions.

The exact monitor controls depend on its model. HDMI coverage of the top and bottom of an open-gate recording was
not compared in this fork's test. Check with objects near both frame edges before relying on the HDMI framing.

## Import custom camera looks

1. Obtain **native camera-look JSON files** compatible with ILCE-7M4 from [M4 Color Lab](https://erlla.github.io/sony-a7m4-custom-firmware/)
   or a properly validated conversion. A normal `.cube` or DCP file cannot be imported by simply renaming it.
2. Extract the files and place them directly in **`PRIVATE/M4ROOT/GENERAL/LUT/`** on the SD card.
3. Open **MENU → Exposure/Color → Color/Tone → Custom LUTs**.
4. Press **Left**, select the card and file, and complete the import/replacement prompts.
5. Select the imported look with the directional controls or by touching the number column. Press **Right** for its
   adjustments; Left/Right selects a control, Up/Down changes it, and confirmation saves it.

There are **16 camera slots**. Each JSON must be nonempty and no larger than **128 KiB**; the import directory supports
at most **256 entries**, including non-JSON files and subdirectories. Filenames including `.json` are limited to
63 UTF-8 bytes. Imported looks are stored internally, so the original card file is not needed for subsequent use.

This feature uses a **native photo/live camera-look parameter format**. It is not documented as a conventional
monitor-only S-Log3 `.cube` loader. For the external-monitor LUT-preview workflow, load a LUT into the monitor using
its supported format and settings. Retain **Rec. Media dur HDMI Output = On** for internal recording. The custom
camera-look import and its interaction with video have not been tested on this fork; do not assume preview-only behavior.

See [LUT operation and limits](../methods/08-custom-lut/README.en.md) and the [native JSON contract](../methods/08-custom-lut/FORMAT.md).

## Check a saved clip

Use the MP4 video stream and decoded frames to verify dimensions: **3840 × 2560** for 4K or **5760 × 3840** for 5.7K.
Sony's XML may still report 3840 × 2160 and the original bitrate label. The recent test decoded both complete 5.7K
files, checked timestamps and exact frame hashes, and confirmed the audio tracks' structure and sample counts.
It did not establish long-take stability, useful microphone level, perceptual sync, HDMI framing or all firmware features.
