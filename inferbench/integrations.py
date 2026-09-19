"""Apply default backend setting to Ollama."""

import os
from pathlib import Path


def apply_backend_to_ollama(backend: str) -> dict:
    if os.name == "nt":
        try:
            import winreg, ctypes
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(key, "OLLAMA_GPU_BACKEND", 0, winreg.REG_SZ, backend)
            winreg.CloseKey(key)
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 2, 5000, ctypes.byref(ctypes.c_long()))
            return {"success": True, "message": f"OLLAMA_GPU_BACKEND set to {backend}. Restart Ollama."}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        bashrc = Path.home() / ".bashrc"
        line = f"export OLLAMA_GPU_BACKEND={backend}  # Added by InferBench\n"
        try:
            existing = bashrc.read_text() if bashrc.exists() else ""
            cleaned = [l for l in existing.splitlines(keepends=True) if "OLLAMA_GPU_BACKEND" not in l]
            with open(bashrc, "w") as f:
                f.writelines(cleaned)
                f.write("\n" + line)
            return {"success": True, "message": f"Added to ~/.bashrc. Restart Ollama."}
        except Exception as e:
            return {"success": False, "error": str(e)}
