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
from a7m4.open_gate import Module, _config_header, _linker_script, build, compose_ap
from a7m4.open_gate_sites import (_CP_IMAGE_VA, _NATIVE, PRESETS, _ROOT, STEP1, _STORED_RECORD, Family, Mode, SiteImage,
                                  Space, check_stock, compile_image, dmmcfg_edits, _layout, load_design)

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
        steps = [s[1] for s in kit["STATES"][state]["steps"] if s[1] not in (STEP1, "lcdcycle_v6")]
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
