"""Manage llama.cpp backend binaries."""

import os
import platform
import shutil
import urllib.request
import zipfile
from .config import BACKENDS_DIR, ensure_dirs

LLAMACPP_RELEASES = {
    "windows": {
        "vulkan": {
            "url": "https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-b4321-bin-win-vulkan-x64.zip",
            "binary": "llama-cli.exe",
        },
        "hip": {
            "url": "https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-b4321-bin-win-hip-x64.zip",
            "binary": "llama-cli.exe",
        },
    },
}


def find_installed_backend(backend: str) -> str | None:
    exe_name = "llama-cli.exe" if platform.system().lower() == "windows" else "llama-cli"
    found = shutil.which(exe_name)
    if found:
        return found
    ensure_dirs()
    backend_dir = BACKENDS_DIR / backend
    if backend_dir.exists():
        for f in backend_dir.rglob(exe_name):
            return str(f)
    return None


def download_backend(backend: str, progress_cb=None) -> str | None:
    ensure_dirs()
    os_name = "windows" if platform.system().lower() == "windows" else "linux"
    if os_name not in LLAMACPP_RELEASES or backend not in LLAMACPP_RELEASES[os_name]:
        return None

    info = LLAMACPP_RELEASES[os_name][backend]
    backend_dir = BACKENDS_DIR / backend
    backend_dir.mkdir(parents=True, exist_ok=True)
    zip_path = backend_dir / "llamacpp.zip"

    try:
        headers = {"User-Agent": "Mozilla/5.0 (InferBench)"}
        req = urllib.request.Request(info["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp, open(zip_path, "wb") as f:
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(8192)
                if not chunk: break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    progress_cb(downloaded, total)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(backend_dir)
        zip_path.unlink(missing_ok=True)

        for f in backend_dir.rglob(info["binary"]):
            return str(f)
        return None
    except Exception:
        return None


def ensure_backend(backend: str, auto_download: bool = False, progress_cb=None) -> str | None:
    existing = find_installed_backend(backend)
    if existing:
        return existing
    if auto_download:
        return download_backend(backend, progress_cb)
    return None
