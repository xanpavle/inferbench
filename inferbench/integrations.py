"""Apply default backend setting to Ollama and LM Studio."""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime


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


def _find_lmstudio_config() -> Path | None:
    """Find LM Studio's local config file path across possible locations."""
    home = Path.home()
    candidates = [
        home / ".lmstudio" / "settings.json",
        home / ".lmstudio" / ".internal" / "user-settings.json",
        home / ".cache" / "lm-studio" / "settings.json",
        home / "AppData" / "Roaming" / "LM Studio" / "settings.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def apply_backend_to_lmstudio(backend: str) -> dict:
    """Modify LM Studio's config to prefer Vulkan or ROCm for GPU inference."""
    config_path = _find_lmstudio_config()
    if not config_path:
        return {
            "success": False,
            "error": "LM Studio settings file not found. Open LM Studio at least once to generate it."
        }

    try:
        # Backup original
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.with_suffix(f".backup.{ts}.json")
        shutil.copy2(config_path, backup_path)

        # Load and modify
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}

        # LM Studio uses different key names across versions
        engine = "vulkan-llm-engine" if backend == "vulkan" else "rocm-llm-engine"
        data["preferredLlmBackend"] = engine
        data["preferredEmbeddingBackend"] = engine
        data["gpu_backend"] = backend
        data["preferred_backend"] = backend

        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        return {
            "success": True,
            "message": f"LM Studio config updated to prefer {backend.upper()} backend.\n  Backup: {backup_path}\n  Restart LM Studio for changes to take effect."
        }
    except PermissionError:
        return {"success": False, "error": "Permission denied writing LM Studio config. Try closing LM Studio first."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def apply_backend_all(backend: str) -> dict:
    """Apply backend to all detected AI runtimes (Ollama + LM Studio)."""
    results = {"ollama": None, "lm_studio": None}
    results["ollama"] = apply_backend_to_ollama(backend)
    results["lm_studio"] = apply_backend_to_lmstudio(backend)
    return results
