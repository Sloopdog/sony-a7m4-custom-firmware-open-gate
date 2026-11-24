"""Use the existing offline builder with prompt collection of ExtFS cycles.

Changes host memory lifetime only. No firmware transformations or validation
checks are replaced, and no camera I/O is performed.
"""
from pathlib import Path
import gc
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from a7m4 import firmware

original = firmware.ext_replace


def bounded_replace(*args, **kwargs):
    result = original(*args, **kwargs)
    gc.collect()
    return result


if __name__ == '__main__':
    firmware.ext_replace = bounded_replace
    runpy.run_module('a7m4.open_gate', run_name='__main__')
