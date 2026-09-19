"""Terminal utility functions, safe subprocess execution, and global installer."""

import os
import platform
import subprocess
import shutil
from pathlib import Path


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


def enable_ansi():
    if platform.system().lower() == "windows":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetConsoleMode(k32.GetStdHandle(-11), 7)
        except Exception:
            for attr in dir(C):
                if not attr.startswith("_") and attr != "RESET":
                    setattr(C, attr, "")
            C.RESET = ""


def safe_run(cmd, shell=False, env=None, timeout=30) -> tuple[str, str, int]:
    """Run a subprocess with UTF-8 encoding and prevent hanging on user input prompts."""
    try:
        e = env if env is not None else os.environ.copy()
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=shell,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=e,
            stdin=subprocess.DEVNULL
        )
        return res.stdout.strip(), res.stderr.strip(), res.returncode
    except Exception as e:
        return "", str(e), -1


def install_globally() -> bool:
    """Register 'inferbench' command globally across all terminals."""
    os_name = "windows" if os.name == "nt" else "linux"
    script_dir = Path(__file__).resolve().parent.parent

    print(f"\n{C.BOLD}{C.CYAN}⚙️  Register 'inferbench' as a global command?{C.RESET}")
    print("  This lets you run 'inferbench' from any terminal/folder.\n")

    try:
        if input("  Install globally? [Y/n]: ").strip().lower() == "n":
            return False
    except Exception:
        return False

    if os_name == "windows":
        try:
            bat_path = script_dir / "inferbench.bat"
            bat_path.write_text(f'@echo off\npython -m inferbench %*\n', encoding="utf-8")

            import winreg, ctypes
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS)
            try:
                path_val, _ = winreg.QueryValueEx(key, "Path")
            except Exception:
                path_val = ""

            if str(script_dir) not in path_val:
                new_path = f"{path_val};{script_dir}" if path_val else str(script_dir)
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 2, 5000, ctypes.byref(ctypes.c_long()))
            winreg.CloseKey(key)
            print(f"\n  {C.GREEN}✓ Registered! Open a NEW terminal window to use it.{C.RESET}\n")
            return True
        except Exception as e:
            print(f"  {C.RED}Failed to set PATH: {e}{C.RESET}")
            return False
    else:
        try:
            local_bin = Path.home() / ".local" / "bin"
            local_bin.mkdir(parents=True, exist_ok=True)
            bin_path = local_bin / "inferbench"
            bin_path.write_text('#!/bin/sh\npython3 -m inferbench "$@"\n', encoding="utf-8")
            bin_path.chmod(0o755)
            print(f"\n  {C.GREEN}✓ Registered at {bin_path}{C.RESET}\n")
            return True
        except Exception as e:
            print(f"  {C.RED}Failed: {e}{C.RESET}")
            return False
