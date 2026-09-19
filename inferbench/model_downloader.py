"""Download lightweight test models if the user has none."""

import urllib.request
from .config import MODELS_DIR, ensure_dirs

TEST_MODELS = {
    "qwen2.5-0.5b": {
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "size_mb": 400,
        "name": "Qwen2.5 0.5B (Q4_K_M)",
    },
    "smollm-135m": {
        "url": "https://huggingface.co/HuggingFaceTB/SmolLM-135M-Instruct-GGUF/resolve/main/smollm-135m-instruct-q4_k_m.gguf",
        "size_mb": 90,
        "name": "SmolLM 135M (Q4_K_M)",
    },
}


def download_model(model_key: str, progress_cb=None) -> str | None:
    if model_key not in TEST_MODELS:
        return None
    ensure_dirs()
    info = TEST_MODELS[model_key]
    dest = MODELS_DIR / f"{model_key}.gguf"
    if dest.exists():
        return str(dest)

    try:
        headers = {"User-Agent": "Mozilla/5.0 (InferBench)"}
        req = urllib.request.Request(info["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(8192)
                if not chunk: break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    progress_cb(downloaded, total)
        return str(dest)
    except Exception:
        if dest.exists(): dest.unlink()
        return None
