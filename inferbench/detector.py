"""Detect GPU + available backends (Vulkan / HIP)."""

import os
import platform
import re
from pathlib import Path
from .utils import safe_run


def detect_os() -> str:
    s = platform.system().lower()
    if s == "windows": return "windows"
    if s == "linux": return "linux"
    if s == "darwin": return "macos"
    return "unknown"


def detect_amd_gpus() -> list[dict]:
    """Detect AMD GPUs via Registry on Windows or lspci on Linux."""
    gpus = []
    if detect_os() == "windows":
        try:
            import winreg
            base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as class_key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(class_key, i)
                        i += 1
                        if subkey_name == "Properties": continue
                        with winreg.OpenKey(class_key, subkey_name) as sk:
                            try: desc = winreg.QueryValueEx(sk, "DriverDesc")[0]
                            except FileNotFoundError: continue
                            if not any(v in desc.lower() for v in ["amd", "radeon", "ati"]): continue
                            pci_id = "unknown"
                            try:
                                mid = winreg.QueryValueEx(sk, "MatchingDeviceId")[0]
                                m = re.search(r"VEN_1002&DEV_([0-9A-Fa-f]{4})", mid)
                                if m: pci_id = m.group(1).lower()
                            except FileNotFoundError: pass
                            driver = "unknown"
                            try: driver = winreg.QueryValueEx(sk, "DriverVersion")[0]
                            except FileNotFoundError: pass
                            if pci_id in ("164e", "1638"): continue
                            gpus.append({"pci_id": pci_id, "name": desc, "driver_version": driver})
                    except OSError: break
        except Exception: pass
    else:
        stdout, _, _ = safe_run(["lspci", "-nn", "-d", "1002::"])
        for line in stdout.splitlines():
            m = re.search(r"\[1002:([0-9a-fA-F]{4})\]", line)
            if m and any(k in line for k in ["VGA", "Display", "3D"]):
                pci_id = m.group(1).lower()
                if pci_id in ("164e", "1638"): continue
                name_m = re.search(r"\]:\s*(.+?)\s*\[1002:", line)
                name = name_m.group(1) if name_m else "AMD GPU"
                gpus.append({"pci_id": pci_id, "name": name, "driver_version": "unknown"})
    return gpus


def check_vulkan() -> dict:
    """Check if Vulkan API is functional."""
    stdout, _, _ = safe_run(["vulkaninfo", "--summary"])
    if not stdout:
        return {"available": False, "version": None}
    ver_match = re.search(r"Vulkan Instance Version:\s*([\d.]+)", stdout)
    return {
        "available": True,
        "version": ver_match.group(1) if ver_match else "unknown",
    }


def check_hip() -> dict:
    """Check if AMD HIP SDK is installed."""
    if detect_os() == "windows":
        hip_path = os.environ.get("HIP_PATH", "")
        if hip_path and Path(hip_path).exists():
            m = re.search(r"[\\\/](\d+\.\d+)[\\\/]?$", hip_path.rstrip("\\/"))
            return {"available": True, "version": m.group(1) if m else "unknown", "path": hip_path}
        return {"available": False, "version": None, "path": None}
    else:
        vf = Path("/opt/rocm/.info/version")
        if vf.exists():
            try:
                return {"available": True, "version": vf.read_text().strip(), "path": "/opt/rocm"}
            except OSError: pass
        return {"available": False, "version": None, "path": None}


def full_scan() -> dict:
    """Run full system diagnostics."""
    return {
        "os": detect_os(),
        "gpus": detect_amd_gpus(),
        "vulkan": check_vulkan(),
        "hip": check_hip(),
    }
