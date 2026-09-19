"""Sanity tests for detector."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from inferbench.detector import detect_os, full_scan


def test_detect_os():
    assert detect_os() in ("windows", "linux", "macos", "unknown")


def test_full_scan_shape():
    scan = full_scan()
    assert "os" in scan
    assert "gpus" in scan
    assert "vulkan" in scan
    assert "hip" in scan
    assert isinstance(scan["gpus"], list)


if __name__ == "__main__":
    print(f"OS: {detect_os()}")
    print(f"Full scan: {full_scan()}")
    print("Tests passed.")
