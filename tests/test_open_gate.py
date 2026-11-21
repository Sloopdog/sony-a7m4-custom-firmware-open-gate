"""Open gate: the site image against the kit's designs and v0.1.3's files, and the camera module on the host.

Needs ArcaneLantern/a7iv-open-gate-test's designs and an unpacked v0.1.3 tree (fwtool); they are not in the repo.
Set OG_DESIGNS and OG_V013_DEV, or keep the workspace layout (../a7iv-open-gate-test, ../out/open-gate/...).
"""
import argparse
import hashlib
import json
import os
import runpy
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from a7m4.common import ToolError
from a7m4.open_gate import (Module, _config_header, _edit_bank, _edit_banks, _linker_script, _uxc_records, _uxc_texts,
                            build, compile_module, compose_ap)
from a7m4.open_gate_sites import (_CP_IMAGE_VA, _NATIVE, PRESETS, _ROOT, STEP1, _STORED_RECORD, Family, Mode, Run, SiteImage,
                                  Space, check_stock, compile_image, dmmcfg_edits, _layout, load_design, runs_of)

WORKSPACE = _ROOT.parent
DESIGNS = Path(os.environ.get("OG_DESIGNS", WORKSPACE / "a7iv-open-gate-test/windows/tools/modding/designs"))
DEV = Path(os.environ.get("OG_V013_DEV", WORKSPACE / "out/open-gate/v013-unpacked/firmware.tar_unpacked/0700_part_image/dev"))
KIT_APPLY = DESIGNS.parents[1] / "camera_tests/CT6_memory_read_check/open_gate_apply.py"
FILES = {"cpapp-b.bin": ("nflasha8_unpacked/cpapp-b.bin", "nflasha8:CPAPP-B.BIN"),
         "av-cam.bin": ("nflasha3_unpacked/av-cam.bin", "nflasha3:av-cam.bin"),
         "libmpr.so": ("nflasha15_unpacked/lib/libmpr.so", "nflasha15:lib/libmpr.so"),
         "DmmCfg.bin": ("nflasha8_unpacked/DmmCfg.bin", "nflasha8:DMMCFG.BIN")}
RECORD = json.loads(_STORED_RECORD.read_text("utf-8"))
OK, BUSY, NOT_READY, WRONG_DIAL, FOREIGN, IO, UNDO_FAILED, NOT_SAVED = range(8)

needs_designs = pytest.mark.skipif(not DESIGNS.is_dir(), reason="kit designs not available")
needs_files = pytest.mark.skipif(not all((DEV / p).is_file() for p, _ in FILES.values()), reason="no v0.1.3 tree")


@pytest.fixture(scope="module")
def image():
    if not DESIGNS.is_dir():
        pytest.skip("kit designs not available")
    return compile_image(DESIGNS, _STORED_RECORD)


@pytest.fixture(scope="module")
def files():
    if not all((DEV / p).is_file() for p, _ in FILES.values()):
        pytest.skip("no unpacked v0.1.3 tree")
    data = {k: (DEV / p).read_bytes() for k, (p, _) in FILES.items()}
    for key, (_, pin) in FILES.items():
        assert hashlib.sha256(data[key]).hexdigest() == _layout()["inputs"][pin], key
    return data


def expected_bytes(mode, family, changed_only=True):
    """{(space, addr): (old, new)} for every changed byte (or every byte) of a preset's design entries and stored
    record patch, read straight from the JSONs."""
    result = {}

    def add(space, addr, old, new):
        for i, (o, n) in enumerate(zip(bytes.fromhex(old), bytes.fromhex(new))):
            if o != n or not changed_only:
                assert result.setdefault((space, addr + i), (o, n)) == (o, n)

    for name in PRESETS[(mode, family)]:
        design = json.loads((DESIGNS / f"{name}.json").read_text())
        for patch in design.get("patches", []):
            space = {"av-cam.bin": Space.AVCAM, "libmpr.so": Space.MPR}.get(patch.get("binary"), Space.CP)
            add(space, int(patch["file_off"] if "binary" in patch else patch["addr"], 16), patch["old"], patch["new"])
        for site in design.get("sites", []):
            add(Space.CP, int(site["ram_address"], 16), site["old"], site["new"])
        if design["summary"].get("plus", "").startswith("26 bytes of the stored drive-parameter record"):
            fam = RECORD["families"][family.value]
            for i, off in enumerate(fam["offsets_in_record"]):
                add(Space.CP_DRIVE_RECORD, off, fam["old"][2 * i:2 * i + 2], fam["new"][2 * i:2 * i + 2])
    return result


def image_bytes(preset):
    result = {}
    for run in preset.runs:
        for i in range(len(run.old)):
            assert (run.space, run.addr + i) not in result
            result[(run.space, run.addr + i)] = (run.old[i], run.new[i])
    return result


@needs_designs
def test_presets_are_the_kit_states_without_step1_and_the_c3_cycle():
    kit = runpy.run_path(str(KIT_APPLY))
    for state, mode in (("default", Mode.UHD_32), ("real57", Mode.K57_32)):
        steps = [s[1] for s in kit["STATES"][state]["steps"] if s[1] != STEP1 and not s[1].startswith("lcdcycle")]
        assert PRESETS[(mode, Family.NTSC)] == tuple(steps)
        pal = [kit["PAL"][s][1] if s in kit["PAL"] else s for s in steps]
        assert PRESETS[(mode, Family.PAL)] == tuple(pal)


def test_site_image_round_trip(image):
    data = image.encode()
    assert SiteImage.decode(data) == image and image.encode() == data
    assert [(p.mode, p.family) for p in image.presets] == list(PRESETS)
    broken = bytearray(data)
    broken[-1] ^= 1
    with pytest.raises(ToolError):
        SiteImage.decode(bytes(broken))
    small = SiteImage(image.presets[:1])
    assert SiteImage.decode(small.encode()) == small


def test_every_run_equals_its_design_entries_and_the_stored_record(image):
    for preset in image.presets:
        want, got = expected_bytes(preset.mode, preset.family), image_bytes(preset)
        covered = expected_bytes(preset.mode, preset.family, changed_only=False)
        assert {k: v for k, v in got.items() if v[0] != v[1]} == want, (preset.mode, preset.family)
        for key, value in got.items():   # unchanged bytes kept inside a run are unchanged bytes of a design entry
            assert covered[key] == value


def test_runs_of_one_space_coincide_or_are_disjoint(image):
    seen = {}
    for preset in image.presets:
        for run in preset.runs:
            key = (run.space, preset.family if run.space is Space.CP_DRIVE_RECORD else None)
            seen.setdefault(key, {}).setdefault(run.addr, len(run.old))
            assert seen[key][run.addr] == len(run.old)
    for runs in seen.values():
        ordered = sorted(runs.items())
        assert all(a + n <= b for (a, n), (b, _) in zip(ordered, ordered[1:]))


def test_check_stock_against_v013(image, files):
    check_stock(image, files)
    run = next(r for r in image.presets[0].runs if r.space is Space.CP and r.addr - _CP_IMAGE_VA < len(files["cpapp-b.bin"]))
    tampered = bytearray(files["cpapp-b.bin"])
    tampered[run.addr - _CP_IMAGE_VA] ^= 0xff
    with pytest.raises(ToolError, match="not stock"):
        check_stock(image, files | {"cpapp-b.bin": bytes(tampered)})


@needs_designs
def test_dmmcfg_edits_are_dmmwb4688_v1(files):
    design = json.loads((DESIGNS / f"{STEP1}.json").read_text())
    edits = dmmcfg_edits(DESIGNS)
    assert [(e.offset, e.old, e.new) for e in edits] == [
        (int(s["file_offset_of_the_same_field"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"]))
        for s in design["sites"]]
    assert sum(len(e.new) for e in edits) == 16
    for e in edits:
        assert files["DmmCfg.bin"][e.offset:e.offset + len(e.old)] == e.old


@needs_designs
def test_load_design_refuses_a_changed_file(tmp_path):
    for name in _layout()["designs"]:
        shutil.copy(DESIGNS / f"{name}.json", tmp_path)
    assert load_design(tmp_path, "lcdfill_v2")["design"] == "lcdfill_v2"
    (tmp_path / "lcdfill_v2.json").write_text((tmp_path / "lcdfill_v2.json").read_text().replace("03000000", "03000001", 1))
    with pytest.raises(ToolError, match="SHA-256"):
        load_design(tmp_path, "lcdfill_v2")


def test_runs_of_takes_code_sites_in_libmpr_only():
    mpr = {"binary": "libmpr.so", "file_off": "0x11f4e0", "va": "0x11f4e0", "old": "2090801a", "new": "00008052", "code": True}
    assert runs_of({"patches": [mpr]}, None) == [Run(Space.MPR, 0x11f4e0, bytes.fromhex("2090801a"), bytes.fromhex("00008052"))]
    with pytest.raises(ToolError, match="libmpr.so only"):
        runs_of({"patches": [dict(mpr, binary="av-cam.bin")]}, None)


def test_native_sources_are_pinned():
    pins = _layout()["sources"]
    for name, value in pins.items():
        assert hashlib.sha256((_NATIVE / name).read_bytes()).hexdigest() == value, name


def test_generated_config_and_linker_script_follow_layout():
    lay = _layout()
    header = _config_header(lay, RECORD)
    assert "#define OG_RECORD_ROOT 0x12b9cc0u" in header and "#define OG_CP_VA_END 0x10000000u" in header
    assert "#define OG_DRIVE_MODE_NTSC 0x8c0u" in header and "#define OG_DRIVE_MODE_PAL 0x880u" in header
    script = _linker_script(lay)
    assert ".text 0x9063000" in script and ".bss 0x907f000" in script
    assert "hook_first_previous = 0x9012bd8;" in script and "dlsym = 0x17166a0;" in script
    assert "#define OG_MENU_MID 1600\n" in header and "#define OG_MENU_ALIAS_BASE 5638\n" in header
    assert "#define OG_MENU_TEXT_TITLE 0x0200ab51\n" in header and "#define OG_MENU_TEXT_OFF 0x0200a00f\n" in header
    for line in ("og_menu_previous_options = 0x90108b8;", "og_menu_previous_blocked = 0x8fb877c;",
                 "og_native_register_leaf = 0x1cd0d90;", "og_native_map_alias = 0x7614328;", "og_native_true = 0x1c9efbc;",
                 "og_menu_apply_custom = 0x1c15604;"):
        assert line in script, line


def build_args(tmp_path, **overrides):
    keys = _ROOT / "keys/published"
    args = {"base": tmp_path / "base.DAT", "designs": DESIGNS, "zig": tmp_path / "zig", "output": tmp_path / "out",
            "private_key": keys / "A7M4_updater_private.pem", "public_key": keys / "A7M4_updater_public.pem"}
    (tmp_path / "base.DAT").write_bytes(b"not v0.1.3")
    (tmp_path / "zig").write_bytes(b"not zig")
    return argparse.Namespace(**(args | overrides))


def test_build_refuses_an_existing_output_and_wrong_inputs(tmp_path):
    (tmp_path / "taken").mkdir()
    with pytest.raises(ToolError, match="new output directory"):
        build(build_args(tmp_path, output=tmp_path / "taken"))
    with pytest.raises(ToolError, match="v0.1.3"):
        build(build_args(tmp_path))
    assert not (tmp_path / "out").exists()
    base = WORKSPACE / "firmware/BODYDATA-custom-v0.1.3.DAT"
    if base.is_file():
        with pytest.raises(ToolError, match="Zig"):
            build(build_args(tmp_path, base=base))
        assert not (tmp_path / "out").exists()


def test_compose_ap_refuses_another_appfw():
    module = Module(b"\0" * 16, 0x9063000, 0x907f000, 0, {})
    with pytest.raises(ToolError, match="v0.1.3"):
        compose_ap(b"\x7fELF" + bytes(64), module, _layout())


# --- og_reconcile.c and og.c on the host, against a fake og_mem seeded with v0.1.3's files --------------------------

class Camera:
    def __init__(self, binary, files, family, image):
        fam = RECORD["families"]
        offsets = ",".join(map(str, fam["ntsc"]["offsets_in_record"]))
        assert fam["ntsc"]["offsets_in_record"] == fam["pal"]["offsets_in_record"]
        self.p = subprocess.Popen([str(binary), str(DEV / FILES["cpapp-b.bin"][0]), str(DEV / FILES["av-cam.bin"][0]),
                                   str(DEV / FILES["libmpr.so"][0]), family.value, offsets, fam["ntsc"]["old"],
                                   fam["pal"]["old"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.family = family
        for preset in image.presets:   # CP RAM beyond the loaded image holds its stock bytes
            for run in preset.runs:
                if run.space is Space.CP and run.addr - _CP_IMAGE_VA >= len(files["cpapp-b.bin"]):
                    assert self.send(f"seed 0 {run.addr} {run.old.hex()}") == ["ok"]

    def send(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()
        return self.p.stdout.readline().split()

    def status(self, line):
        words = self.send(line)
        return int(words[1]), int(words[3]), int(words[5])

    def diff(self):
        self.p.stdin.write("diff\n")
        self.p.stdin.flush()
        result = {}
        for line in iter(self.p.stdout.readline, "end\n"):
            kind, a, b, c = line.split()
            result[(Space.CP_DRIVE_RECORD, int(b), int(a)) if kind == "r" else (Space(int(a)), int(b))] = int(c)
        return result

    def close(self):
        self.p.stdin.close()
        assert self.p.wait(timeout=60) == 0


def state_of(mode, family):
    """The diff the fake memory must show with a mode applied: every changed design byte at its new value."""
    if mode is Mode.OFF:
        return {}
    index = 0 if family is Family.NTSC else 1
    return {((s, a, index) if s is Space.CP_DRIVE_RECORD else (s, a)): new
            for (s, a), (_, new) in expected_bytes(mode, family).items()}


@pytest.fixture(scope="module")
def host(image, files, tmp_path_factory):
    clang = shutil.which("clang") or shutil.which("cc")
    if not clang:
        pytest.skip("no host C compiler")
    tmp = tmp_path_factory.mktemp("og_host")
    (tmp / "setting").mkdir()
    blob = image.encode()
    (tmp / "og_sites_host.c").write_text(
        "#include <stdint.h>\n_Alignas(8) const uint8_t og_sites[] = {" + ",".join(map(str, blob)) + "};\n")
    (tmp / "og_config.h").write_text(_config_header(_layout(), RECORD))
    binary = tmp / "og_host"
    subprocess.run([clang, "-std=c11", "-D_DEFAULT_SOURCE", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-fno-strict-aliasing",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-DOG_HOST",
                    f"-DOG_SETTING_DIR=\"{tmp / 'setting'}\"", "-I", str(_NATIVE), "-I", str(tmp),
                    str(_ROOT / "tests/native/og_host.c"), str(_NATIVE / "og_reconcile.c"), str(_NATIVE / "og.c"),
                    str(tmp / "og_sites_host.c"), "-o", str(binary)], check=True)
    return binary


@pytest.fixture
def setting(host):
    """/setting for og.c in the harness, empty at the start of each test."""
    directory = host.parent / "setting"
    for item in directory.iterdir():
        item.unlink()
    return directory


@pytest.fixture
def camera(host, image, files, setting, request):
    cam = Camera(host, files, getattr(request, "param", Family.NTSC), image)
    yield cam
    cam.close()


both = pytest.mark.parametrize("camera", [Family.NTSC, Family.PAL], indirect=True, ids=["ntsc", "pal"])


@both
def test_reconcile_reaches_each_mode_and_back_to_stock(camera):
    fam = camera.family
    assert camera.status("reconcile 0")[::2] == (OK, 0)
    assert camera.diff() == {}
    assert camera.status("reconcile 1")[0] == OK
    assert camera.diff() == state_of(Mode.UHD_32, fam)
    status, reads, writes = camera.status("reconcile 1")
    assert (status, writes) == (OK, 0) and reads
    assert camera.status("reconcile 2")[0] == OK
    assert camera.diff() == state_of(Mode.K57_32, fam)
    assert camera.status("reconcile 2")[::2] == (OK, 0)
    assert camera.status("reconcile 1")[0] == OK
    assert camera.diff() == state_of(Mode.UHD_32, fam)
    assert camera.status("reconcile 0")[0] == OK
    assert camera.diff() == {}


@both
def test_foreign_bytes_are_refused_with_nothing_written(camera, image):
    preset = next(p for p in image.presets if p.family is camera.family and p.mode is Mode.K57_32)
    run = next(r for r in preset.runs if r.space is Space.AVCAM)
    foreign = bytes(b ^ 0x5a for b in run.old)
    assert foreign not in (run.old, run.new)
    assert camera.send(f"corrupt 2 {run.addr} {foreign.hex()}") == ["ok"]
    before = camera.diff()
    assert camera.status("reconcile 2")[::2] == (FOREIGN, 0)
    assert camera.status("reconcile 0")[::2] == (FOREIGN, 0)
    assert camera.diff() == before


@both
def test_foreign_stored_record_is_refused(camera, image):
    fam = RECORD["families"][camera.family.value]
    index = 0 if camera.family is Family.NTSC else 1
    camera.send(f"corrupt 1 {fam['offsets_in_record'][0]} ff")   # the record of the camera's own family
    assert camera.status("reconcile 1")[::2] == (FOREIGN, 0)
    assert camera.diff() == {(Space.CP_DRIVE_RECORD, fam["offsets_in_record"][0], index): 0xff}


@pytest.mark.parametrize("how", ["before", "after"])
@pytest.mark.parametrize("nth", [1, 2, 40, 300, 640])
def test_a_failed_write_puts_every_site_back(camera, nth, how):
    assert camera.status("reconcile 1")[0] == OK
    start = camera.diff()
    camera.send(f"fail {nth} {how}")
    status, _, writes = camera.status("reconcile 2")
    if writes < nth:   # the transition needs fewer writes: nothing failed
        assert status == OK
        return
    assert status == IO
    assert camera.diff() == start
    camera.send(f"fail {nth} {how}")
    status, _, writes = camera.status("reconcile 0")
    assert (status, camera.diff()) == ((IO, start) if writes >= nth else (OK, {}))


def test_a_failed_first_apply_leaves_stock(camera):
    camera.send("fail 10 after")
    assert camera.status("reconcile 2")[0] == IO
    assert camera.diff() == {}


def test_a_failed_put_back_reports_undo_failed(camera):
    camera.send("fail 10 all")
    assert camera.status("reconcile 1")[0] == UNDO_FAILED


def test_not_ready_writes_nothing(camera):
    camera.send("ready 0")
    assert camera.status("reconcile 1")[::2] == (NOT_READY, 0)
    camera.send("ready 1")
    assert camera.status("reconcile 1")[0] == OK


def test_select_persists_and_power_on_restores(host, image, files, setting):
    first = Camera(host, files, Family.NTSC, image)
    assert first.send("selected") == ["mode", "0"]
    assert first.send("power_on") == ["reads", "0", "writes", "0"]   # Off and nothing applied: no memory access
    assert first.send("dial 3") == ["ok"]
    assert first.status("select 1")[0] == WRONG_DIAL
    assert first.send("dial 0") == ["ok"]
    assert first.status("select 1")[0] == OK
    assert first.send("selected") == ["mode", "1"]
    assert first.diff() == state_of(Mode.UHD_32, Family.NTSC)
    record = (setting / "open_gate.dat").read_bytes()
    assert record == struct.pack("<4sIII", b"OGT1", 1, 1, 0xfffffffe)
    assert not (setting / "open_gate.tmp").exists()
    first.close()

    second = Camera(host, files, Family.NTSC, image)
    assert second.send("dial 3") == ["ok"]
    assert second.send("power_on")[3] == "0"        # movie: nothing written
    assert second.diff() == {}
    assert second.send("dial 0") == ["ok"]
    second.send("power_on")
    assert second.diff() == state_of(Mode.UHD_32, Family.NTSC)
    assert second.send("power_on")[3] == "0"        # already in place: reads only
    assert second.status("select 0")[0] == OK
    assert second.diff() == {} and second.send("load") == ["mode", "0"]
    second.close()


def test_bad_record_files_mean_off(host, image, files, setting):
    for content in (b"", b"OGT1" + bytes(12), struct.pack("<4sIII", b"OGT1", 1, 1, 1),
                    struct.pack("<4sIII", b"OGT1", 2, 1, 0xfffffffe), struct.pack("<4sIII", b"OGT1", 1, 7, ~7 & 0xffffffff),
                    struct.pack("<4sIII", b"OGT1", 1, 2, 0xfffffffd) + b"x"):
        (setting / "open_gate.dat").write_bytes(content)
        cam = Camera(host, files, Family.NTSC, image)
        assert cam.send("load") == ["mode", "0"], content
        cam.close()
    (setting / "open_gate.dat").write_bytes(struct.pack("<4sIII", b"OGT1", 1, 2, 0xfffffffd))
    cam = Camera(host, files, Family.NTSC, image)
    assert cam.send("load") == ["mode", "2"]
    cam.close()


# --- og_mem.c on the host, unchanged, against fake DMA, /dev/mem and /proc/self/maps --------------------------------

def test_og_mem_on_the_host(image, tmp_path):
    clang = shutil.which("clang") or shutil.which("cc")
    if not clang:
        pytest.skip("no host C compiler")
    blob = image.encode()
    (tmp_path / "og_sites_host.c").write_text(
        "#include <stdint.h>\n_Alignas(8) const uint8_t og_sites[] = {" + ",".join(map(str, blob)) + "};\n")
    (tmp_path / "og_config.h").write_text(_config_header(_layout(), RECORD))
    fam = RECORD["families"]
    assert fam["ntsc"]["offsets_in_record"] == fam["pal"]["offsets_in_record"]
    c_bytes = lambda h: ",".join(str(b) for b in bytes.fromhex(h))
    (tmp_path / "og_mem_seed.h").write_text(
        "static const unsigned seed_off[] = {" + ",".join(map(str, fam["ntsc"]["offsets_in_record"])) + "};\n"
        f"static const uint8_t seed_ntsc_old[] = {{{c_bytes(fam['ntsc']['old'])}}};\n"
        f"static const uint8_t seed_pal_old[] = {{{c_bytes(fam['pal']['old'])}}};\n")
    binary = tmp_path / "og_mem_host"
    subprocess.run([clang, "-std=c11", "-D_DEFAULT_SOURCE", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                    "-fno-strict-aliasing", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    "-I", str(_NATIVE), "-I", str(tmp_path), str(_ROOT / "tests/native/og_mem_host.c"),
                    str(tmp_path / "og_sites_host.c"), "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok read above the cached page" in result.stdout and "ok detect pal, chain ascending" in result.stdout


# --- PR 2: the Open Gate menu item -----------------------------------------------------------------------------------

APP = DEV / "nflasha15_unpacked/share/app"
APPFW = DEV / "nflasha15_unpacked/lib/appFw.so"
STOCK_APP = Path(os.environ.get("OG_602_DEV", WORKSPACE / "unpacked/BODYDATA-6.02/firmware.tar_unpacked/0700_part_image/dev")) \
    / "nflasha15_unpacked/share/app"
ZIG = Path(os.environ.get("OG_ZIG", WORKSPACE / "tools/zig-aarch64-macos-0.15.2/zig"))
MENU = _layout()["menu"]
MID, ALIAS = MENU["mid"], MENU["alias_base"]
TEXT = {k: int(v, 16) for k, v in MENU["text"].items()}
OPTION_TEXT = (TEXT["off"], TEXT["uhd_32"], TEXT["k57_32"])
# The template fields og_menu.c changes from v0.1.3's Volume records (layout.json "menu"."templates").
LEAF_PATCHES = {0x00: TEXT["title"], 0x0c: 0xffffffff, 0x14: 0xca4, 0x54: 3, 0x60: 0xffffffff, 0xbc: 0xca4}
ROW_PATCHES = {0x10: 0xffffffff, 0x20: 0xffffffff, 0x24: 0xffffffff}   # plus alias, text and value per row
PROFILE_PATCHES = {0x00: MID}
# Volume's pointer fields and the symbols that replace them.
LEAF_POINTERS = {0x58: (0x8ff8160, "rows"), 0x70: (0x1c9efbc, "og_native_true"), 0x78: (0x8fb8668, "og_menu_getter"),
                 0x80: (0x8fb86b4, "og_menu_setter"), 0x88: (0x8fb86ec, "og_menu_commit"),
                 0xa8: (0x8f98430, "og_menu_default")}
PROFILE_POINTERS = {0x48: (0x1c9efbc, "og_native_true"), 0x50: (0x8fb876c, "og_menu_profile_blocked")}

needs_appfw = pytest.mark.skipif(not APPFW.is_file(), reason="no v0.1.3 tree")


class Image:
    """v0.1.3's appFw.so (or a composed one) by VA, with its R_AARCH64_RELATIVE table."""

    def __init__(self, data):
        import io
        import numpy as np
        from elftools.elf.elffile import ELFFile
        self.data = data
        self.elf = ELFFile(io.BytesIO(data))
        self.loads = [s for s in self.elf.iter_segments() if s["p_type"] == "PT_LOAD"]
        rela = self.elf.get_section_by_name(".rela.dyn")
        self.rela = np.frombuffer(data, dtype="<u8", count=rela["sh_size"] // 8, offset=rela["sh_offset"]).reshape(-1, 3)

    def offset(self, va):
        s = next(s for s in self.loads if s["p_vaddr"] <= va < s["p_vaddr"] + s["p_filesz"])
        return s["p_offset"] + va - s["p_vaddr"]

    def bytes(self, va, n):
        return self.data[self.offset(va):self.offset(va) + n]

    def u32(self, va):
        return struct.unpack("<I", self.bytes(va, 4))[0]

    def relative(self, va):
        rows = self.rela[(self.rela[:, 0] == va) & (self.rela[:, 1] == 1027)]
        return int(rows[0, 2]) if len(rows) else None

    def branch(self, va):
        word = self.u32(va)
        imm = word & 0x3ffffff
        return {0x94000000: "bl", 0x14000000: "b"}.get(word & 0xfc000000), va + 4 * (imm - ((imm & 0x2000000) << 1))

    def table(self, base, entries, stride):
        return [self.u32(base + stride * i) for i in range(entries)]


@pytest.fixture(scope="module")
def v013():
    if not APPFW.is_file():
        pytest.skip("no v0.1.3 tree")
    data = APPFW.read_bytes()
    assert hashlib.sha256(data).hexdigest() == _layout()["inputs"]["nflasha15:lib/appFw.so"]
    return Image(data)


def patched(record, patches):
    out = bytearray(record)
    for at, value in patches.items():
        struct.pack_into("<I", out, at, value)
    return bytes(out)


def parse_record(text):
    """og_menu_host's record dump: bytes, with '<symbol>' for each pointer field -> (bytes with zeros, {offset: symbol})."""
    out, pointers, i = bytearray(), {}, 0
    while i < len(text):
        if text[i] == "<":
            end = text.index(">", i)
            pointers[len(out)] = text[i + 1:end]
            out.extend(bytes(8))
            i = end + 1
        else:
            out.append(int(text[i:i + 2], 16))
            i += 2
    return bytes(out), pointers


@pytest.fixture(scope="module")
def menu_host(tmp_path_factory):
    clang = shutil.which("clang") or shutil.which("cc")
    if not clang:
        pytest.skip("no host C compiler")
    tmp = tmp_path_factory.mktemp("og_menu_host")
    (tmp / "og_config.h").write_text(_config_header(_layout(), RECORD))
    binary = tmp / "og_menu_host"
    subprocess.run([clang, "-std=c11", "-D_DEFAULT_SOURCE", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-fno-strict-aliasing",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-I", str(_NATIVE), "-I", str(tmp),
                    str(_ROOT / "tests/native/og_menu_host.c"), str(_NATIVE / "og_menu.c"), "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert not [line for line in lines if line.startswith("FAIL")]
    maps = {w[1]: [tuple(e.split(",")) for e in w[3:]] for w in (line.split() for line in lines) if w[0] == "map"}
    records = {w[1]: parse_record(w[2]) for w in (line.split() for line in lines) if w[0] == "record"}
    return lines, maps, records


def test_og_menu_callbacks_on_the_host(menu_host):
    lines, _, _ = menu_host
    for check in ("getter reflects og_selected", "setter stages the browsed value", "commit selects the option's mode",
                  "commit reports any other status as failure", "a failed commit drops the staged value",
                  "commit refuses an alias below the item's", "commit refuses an alias above the item's",
                  "blocked is 1 exactly in movie", "the profile callback agrees", "blocked is 0 without a dial",
                  "the item never reaches the previous check", "other mids chain to the previous check"):
        assert f"ok {check}" in lines, check
    assert lines.count("ok commit reports any other status as failure") == 7   # OG_BUSY .. OG_NOT_SAVED


def test_og_menu_registers_the_item_in_six_maps(menu_host):
    _, maps, _ = menu_host
    aliases = [str(ALIAS + i) for i in range(3)]
    assert maps["leaf"] == [(str(MID), "leaf")] and maps["profile"] == [(str(MID), "profile")]
    assert maps["option"] == [(a, f"row{i}") for i, a in enumerate(aliases)]
    assert maps["parent"] == [(a, str(MID)) for a in aliases]
    assert maps["value"] == maps["alias"] == [(a, a) for a in aliases]


@needs_appfw
def test_og_menu_records_are_volumes_with_the_listed_fields_changed(menu_host, v013):
    _, _, records = menu_host
    templates = {k: int(v, 16) for k, v in MENU["templates"].items() if k != "what"}
    volume_leaf, volume_row = v013.bytes(templates["leaf"], 0xc0), v013.bytes(templates["option"], 0x80)
    volume_profile = v013.bytes(templates["profile"], 0x80)
    for record, pointers in ((volume_leaf, LEAF_POINTERS), (volume_profile, PROFILE_POINTERS)):
        base = templates["leaf"] if record is volume_leaf else templates["profile"]
        for at, (target, _) in pointers.items():
            assert struct.unpack_from("<Q", record, at)[0] == target and v013.relative(base + at) == target
    leaf, leaf_pointers = records["leaf"]
    assert leaf_pointers == {at: name for at, (_, name) in LEAF_POINTERS.items()}
    blank = {at: 0 for at in LEAF_POINTERS} | {at + 4: 0 for at in LEAF_POINTERS}
    assert leaf == patched(volume_leaf, blank | LEAF_PATCHES)
    for i in range(3):
        row, row_pointers = records[f"row{i}"]
        assert not row_pointers
        assert row == patched(volume_row, ROW_PATCHES | {0x00: ALIAS + i, 0x04: ALIAS + i, 0x08: OPTION_TEXT[i], 0x34: i})
    profile, profile_pointers = records["profile"]
    assert profile_pointers == {at: name for at, (_, name) in PROFILE_POINTERS.items()}
    blank = {at: 0 for at in PROFILE_POINTERS} | {at + 4: 0 for at in PROFILE_POINTERS}
    assert profile == patched(volume_profile, blank | PROFILE_PATCHES)


@needs_appfw
def test_menu_ids_are_unused_in_v013(v013):
    """The mid and aliases are in no native table, no custom-firmware registration and no menu group."""
    leaves = set(v013.table(0x50d6f80, 1473, 16)) | {1589, 1591, 1593, 1594, 1596, 1597, 1598, 1599}
    profiles = set(v013.table(0x50f2900, 820, 16)) | {1589, 1591} | set(range(1592, 1600))
    pages = set(v013.table(0x50f5c40, 116, 16)) | {1592, 1595}
    assert MID not in leaves | profiles | pages and max(leaves) < MID
    custom = {0x8f6ce70: 16, 0x8fc0a80: 4, 0x8ff8e00: 20, 0x9020400: 4}   # LUT, sounds, volume, aspect option rows
    options = set(range(5591)) | {a for base, n in custom.items() for a in v013.table(base, n, 16)} | set(range(5631, 5638))
    assert not {ALIAS, ALIAS + 1, ALIAS + 2} & options and max(options) < ALIAS
    for base in (0x3eb07a0, 0x3edbf78, 0x3ee6e30):   # native parent, value and alias tables
        assert not {ALIAS, ALIAS + 1, ALIAS + 2} & set(v013.table(base, 5591, 8))
    tree, tabs = 0x50f6380, v013.u32(0x50f6380)
    for tab in range(tabs):
        for g in range(v013.u32(tree + 8 + tab * 0x2e10 + 8)):
            group = tree + 8 + tab * 0x2e10 + 16 + g * 0x2e0
            assert MID not in v013.table(group + 16, v013.u32(group + 8), 24)


@needs_appfw
def test_image_quality_rec_has_no_free_slot(v013):
    """Why placement is open: the group File Format sits in holds all 30 of its fixed slots."""
    shooting = 0x50f6380 + 8 + 2 * 0x2e10
    group = shooting + 16
    assert v013.u32(shooting) == 2 and v013.u32(group + 4) == 0x0200606e   # tab 'Shooting', group 'Image Quality/Rec'
    assert v013.u32(group + 8) == 30 and 16 + 30 * 24 == 0x2e0
    assert 27 in v013.table(group + 16, 30, 24) and 34 in v013.table(group + 16, 30, 24)   # both File Format items


@pytest.fixture(scope="module")
def composed(image, v013, tmp_path_factory):
    if not ZIG.is_file():
        pytest.skip("pinned Zig not available")
    module = compile_module(ZIG, image, tmp_path_factory.mktemp("og_module") / "module")
    return module, Image(compose_ap(v013.data, module, _layout()))


def test_composed_appfw_changes_only_the_listed_places(composed, v013):
    import numpy as np
    module, out = composed
    differ = np.flatnonzero(np.frombuffer(v013.data, np.uint8) != np.frombuffer(out.data, np.uint8))
    hooks = [v013.offset(int(h["va"], 16)) for h in _layout()["hooks"]]
    allowed = [(0x38, 0x3a), (0x5e73000, 0x5e73000 + len(module.text)), (0x5e80000, 0x5e80000 + 17 * 56)]
    allowed += [(at, at + 4) for at in hooks]
    assert all(any(lo <= int(i) < hi for lo, hi in allowed) for i in differ)
    assert {v013.offset(int(h["va"], 16)) for h in _layout()["hooks"]} <= {int(i) & ~3 for i in differ}


def test_composed_hooks_reach_the_module_and_chain_to_the_previous_heads(composed, v013):
    module, out = composed
    for hook in _layout()["hooks"]:
        va = int(hook["va"], 16)
        assert v013.branch(va) == (hook["kind"], int(hook["previous_target"], 16))
        assert out.branch(va) == (hook["kind"], module.symbols[hook["entry"]])
    calls = {"og_menu_hook_options": ("og_menu_previous_options", "og_menu_register_options"),
             "og_menu_hook_parent": ("og_menu_previous_parent", "og_menu_register_parent"),
             "og_menu_hook_alias": ("og_menu_previous_alias", "og_menu_register_alias")}
    previous = {h["previous_symbol"]: int(h["previous_target"], 16) for h in _layout()["hooks"]}
    for entry, (before, register) in calls.items():
        at = module.symbols[entry]
        assert out.u32(at) == 0xa9bf7bfd and out.u32(at + 4) == 0x910003fd   # stp x29, x30, [sp, #-16]!; mov x29, sp
        assert out.branch(at + 8) == ("bl", previous[before]) and out.branch(at + 12) == ("bl", module.symbols[register])


def test_composed_filters_handle_only_the_item(composed):
    module, out = composed
    previous = {h["entry"]: int(h["previous_target"], 16) for h in _layout()["hooks"]}
    movz = lambda reg, imm: 0x52800000 | (imm << 5) | reg

    def b_ne(at):
        word = out.u32(at)
        assert word & 0xff00001f == 0x54000001
        imm = (word >> 5) & 0x7ffff
        return at + 4 * (imm - ((imm & 0x40000) << 1))

    for name, result in (("og_menu_supported", movz(0, 1)), ("og_menu_mapped", 0x2a0103e0)):   # mov w0, #1 / mov w0, w1
        at = module.symbols[name]
        assert [out.u32(at + 4 * k) for k in (0, 1)] == [movz(16, MID), 0x6b10003f]   # cmp w1, w16
        assert b_ne(at + 8) == previous[name] and out.u32(at + 12) == result and out.u32(at + 16) == 0xd65f03c0
    at = module.symbols["og_menu_apply"]
    assert out.u32(at + 8) == 0xeb10029f   # cmp x20, x16 (x16 = og_menu_records by adrp/add)
    assert out.branch(at + 16) == ("b", int(MENU["stock"]["apply_custom"]["va"], 16))
    assert b_ne(at + 12) == at + 20 and out.branch(at + 20) == ("b", previous["og_menu_apply"])
    at = module.symbols["og_menu_profile_blocked"]
    assert out.u32(at) == movz(0, MID) and out.branch(at + 4) == ("b", module.symbols["og_menu_blocked"])
    at = module.symbols["og_menu_default"]
    assert [out.u32(at), out.u32(at + 4)] == [0x2a1f03e0, 0xd65f03c0]


def test_composed_templates_and_records(composed, menu_host):
    module, out = composed
    _, _, records = menu_host
    leaf, _ = records["leaf"]
    assert out.bytes(module.symbols["leaf_template"], 0xc0) == leaf
    profile, _ = records["profile"]
    assert out.bytes(module.symbols["profile_template"], 0x80) == profile
    row, _ = records["row0"]
    assert out.bytes(module.symbols["row_template"], 0x80) == patched(row, {0x00: 0, 0x04: 0, 0x08: 0, 0x34: 0})
    assert [out.u32(module.symbols["option_text"] + 4 * i) for i in range(3)] == list(OPTION_TEXT)
    rw = next(s for s in out.loads if s["p_vaddr"] == 0x907f000)
    records_va = module.symbols["og_menu_records"]
    assert rw["p_flags"] == 6 and rw["p_vaddr"] <= records_va and records_va + 0x2c0 <= rw["p_vaddr"] + rw["p_memsz"]


def test_menu_stock_checks_refuse_another_layout(v013):
    from a7m4.open_gate import _check_menu_stock
    lay = _layout()
    _check_menu_stock(v013.data, v013.elf, v013.loads, lay)
    tampered = bytearray(v013.data)
    tampered[v013.offset(int(MENU["registrars"]["leaf"], 16))] ^= 1
    with pytest.raises(ToolError, match="leaf registrar"):
        _check_menu_stock(bytes(tampered), v013.elf, v013.loads, lay)
    moved = json.loads(json.dumps(lay))
    moved["menu"]["maps"]["alias"]["va"] = "0x7614330"
    with pytest.raises(ToolError, match="alias map"):
        _check_menu_stock(v013.data, v013.elf, v013.loads, moved)


# --- the 68 string banks -----------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def banks():
    if not APP.is_dir():
        pytest.skip("no v0.1.3 tree")
    return _edit_banks(lambda path: (APP.parent.parent / path).read_bytes(), MENU["strings"])


SHORTENED = {"0x0200ab5e", "0x0200ab61", "0x0200ab62", "0x0200ab63"}
CHINESE = {"simplifiedchinese", "traditionalchinese"}


def test_every_bank_holds_the_labels_and_keeps_its_size(banks):
    assert len(banks) == 68
    for path, (old, new, evidence) in banks.items():
        texts = _uxc_texts(new)
        assert len(new) == len(old), path
        assert [texts[TEXT[k]] for k in ("title", "uhd_32", "k57_32")] == ["Open Gate", "4K 3:2", "5.7K 3:2"], path
        assert texts[TEXT["off"]] == _uxc_texts(old)[TEXT["off"]]   # Sony's own Off, unchanged
        chinese = path.split("_")[1] in CHINESE
        assert set(evidence["shortened"]) == (SHORTENED - {"0x0200ab5e"} if chinese else SHORTENED), path
        assert evidence["label_bytes"] == 44 and evidence["freed_bytes"] == (48 if chinese else 44)


def test_banks_change_only_the_labels_and_the_listed_texts(banks):
    rows = {(r["from"], r["to"]) for r in MENU["strings"]["shorten"]}
    for path, (old, new, evidence) in banks.items():
        before, after = _uxc_texts(old), _uxc_texts(new)
        changed = {rid for rid in before.keys() | after.keys() if before.get(rid) != after.get(rid)}
        assert changed == {TEXT["title"], TEXT["uhd_32"], TEXT["k57_32"]} | {int(k, 16) for k in evidence["shortened"]}
        assert all(tuple(pair) in rows for pair in evidence["shortened"].values())
        records = _uxc_records(new)
        assert all(start + 4 + len(text) < len(new) for start, _, text in records)
        last = max(start for start, rid, _ in _uxc_records(old) if f"{rid:#010x}" in evidence["shortened"])
        tail = min(start for start, _, _ in _uxc_records(old) if start > last)
        assert new[tail:] == old[tail:], path   # every record after the last shortened one keeps its offset


@pytest.mark.skipif(not STOCK_APP.is_dir(), reason="no stock 6.02 tree")
def test_banks_keep_every_sony_string(banks):
    for path, (old, new, _) in banks.items():
        stock, after = _uxc_texts((STOCK_APP.parent.parent / path).read_bytes()), _uxc_texts(new)
        assert {rid: after.get(rid) for rid in stock} == stock, path
        assert not {TEXT["title"], TEXT["uhd_32"], TEXT["k57_32"]} & stock.keys()


def test_edit_bank_refuses_what_it_cannot_do():
    path = APP / "string_english_horizontal.uxc"
    if not path.is_file():
        pytest.skip("no v0.1.3 tree")
    data, strings = path.read_bytes(), MENU["strings"]
    with pytest.raises(ToolError, match="not empty"):
        _edit_bank(data, strings | {"add": {"0x0200ab5c": "taken"}})
    with pytest.raises(ToolError, match="No listed text"):
        _edit_bank(data, strings | {"shorten": [{"id": "0x0200ab61", "from": "other", "to": "x"}]})
    with pytest.raises(ToolError, match="do not free enough"):
        _edit_bank(data, strings | {"shorten": strings["shorten"][1:2]})
