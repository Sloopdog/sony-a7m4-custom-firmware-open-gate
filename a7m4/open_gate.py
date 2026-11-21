"""Build an open-gate BODYDATA.DAT from Erlla custom firmware v0.1.3. Offline only; never opens USB.

    python -m a7m4.open_gate build --base BODYDATA-custom-v0.1.3.DAT --designs <kit>/windows/tools/modding/designs \
        --zig <zig> --private-key keys/published/A7M4_updater_private.pem \
        --public-key keys/published/A7M4_updater_public.pem --output out/open-gate

Contract stub: bodies not implemented.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .fat import Fat
from .open_gate_sites import FileEdit, SiteImage


@dataclass(frozen=True)
class Module:
    text: bytes
    text_va: int
    state_va: int
    state_bytes: int
    symbols: Mapping[str, int]


def compile_module(zig: Path, image: SiteImage, workdir: Path) -> Module:
    """Write image.encode() as og_sites.bin and link native/open-gate at layout.json's fixed VAs."""
    raise NotImplementedError


def compose_ap(appfw: bytes, module: Module, layout: dict) -> bytes:
    """Place the module in appFw.so's zero gap, add its program headers and hooks; same length as the input."""
    raise NotImplementedError


def apply_file_edits(fat: Fat, edits: Sequence[FileEdit]) -> None:
    raise NotImplementedError


def build(args: argparse.Namespace) -> dict:
    """decode -> check_stock -> DmmCfg.bin -> compile_module -> compose_ap -> ext_replace -> sums -> encode -> resign."""
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
