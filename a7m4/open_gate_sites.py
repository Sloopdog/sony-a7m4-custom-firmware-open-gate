"""Open-gate site image: the one source of every address and byte the camera module touches.

Derived at build time from ArcaneLantern/a7iv-open-gate-test's design JSONs and native/open-gate/stored_record.json;
the generated og_sites.bin is never committed. Offline only. Contract stub: bodies not implemented.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path


class Mode(IntEnum):
    OFF = 0
    UHD_32 = 1   # 3840x2560
    K57_32 = 2   # 5760x3840, 300 Mbps


class Space(IntEnum):
    CP = 0
    CP_DRIVE_RECORD = 1
    AVCAM = 2
    MPR = 3


class Family(Enum):
    NTSC = "ntsc"
    PAL = "pal"


@dataclass(frozen=True)
class Run:
    space: Space
    addr: int
    old: bytes
    new: bytes


@dataclass(frozen=True)
class Preset:
    mode: Mode
    family: Family
    runs: tuple[Run, ...]


@dataclass(frozen=True)
class FileEdit:
    """A build-time edit of a file inside a partition (step 1, DmmCfg.bin)."""
    member: str
    path: str
    offset: int
    old: bytes
    new: bytes


@dataclass(frozen=True)
class SiteImage:
    presets: tuple[Preset, ...]

    def encode(self) -> bytes:
        raise NotImplementedError

    @staticmethod
    def decode(data: bytes) -> SiteImage:
        raise NotImplementedError


# Designs per preset, in the kit's apply order (open_gate_apply.py STATES), without step 1 (baked into
# DmmCfg.bin) and without the C3 cycle.
PRESETS: dict[tuple[Mode, Family], tuple[str, ...]] = {
    (Mode.UHD_32, Family.NTSC): ("ogsq_v3", "outsz2560_v1", "ogfile2560_hs_s_v1", "lcdfill_v2"),
    (Mode.UHD_32, Family.PAL): ("ogsq880_v1", "outsz2560_v1", "ogfile2560_hs_s_v1", "lcdfill_v2"),
    (Mode.K57_32, Family.NTSC): ("og57n_v1", "og57cp_v3", "ogfile57r300_v1", "lcdfill_v2"),
    (Mode.K57_32, Family.PAL): ("og57n880_v1", "og57cp_v3", "ogfile57r300_v1", "lcdfill_v2"),
}
STEP1 = "dmmwb4688_v1"


def load_design(designs: Path, name: str) -> dict:
    raise NotImplementedError


def runs_of(design: dict, record_patch: dict | None) -> list[Run]:
    raise NotImplementedError


def compile_image(designs: Path, stored_record: Path) -> SiteImage:
    raise NotImplementedError


def dmmcfg_edits(designs: Path) -> list[FileEdit]:
    raise NotImplementedError


def check_stock(image: SiteImage, files: Mapping[str, bytes]) -> None:
    """Raise unless every file-backed run's old bytes are in the given input files."""
    raise NotImplementedError
