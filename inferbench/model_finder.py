"""Find LM Studio and Ollama models (prefers official runtime IDs)."""

from pathlib import Path
from .utils import safe_run


def is_valid_text_model(name: str, size_gb: float) -> bool:
    """Filter out vision projectors (mmproj), embeddings, and empty categories."""
    nl = name.lower()
    if "mmproj" in nl:
        return False
    if "text-embedding" in nl or "nomic-embed" in nl:
        return False
    if size_gb == 0.0:
        return False
    return True


def find_lmstudio_models() -> list[dict]:
    """Scan LM Studio models using official CLI IDs first."""
    found = []
    seen = set()

    # 1. Query official LM Studio CLI
    stdout, stderr, code = safe_run(["lms", "ls"], timeout=60)
    text = (stdout or "") + "\n" + (stderr or "")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith(("you have", "identifier", "name", "params", "---", "path", "size")):
            continue

        parts = line.split()
        if not parts:
            continue
        mid = parts[0]
        if mid.lower() in ("identifier", "model", "name", "llm", "embedding"):
            continue
        if mid in seen or mid.endswith(".gguf"):
            continue

        size_gb = 0.0
        for i, p in enumerate(parts):
            if p.upper() in ("GB", "MB") and i > 0:
                try:
                    val = float(parts[i - 1].replace(",", ""))
                    size_gb = val if p.upper() == "GB" else val / 1024.0
                except ValueError:
                    pass
                break

        if is_valid_text_model(mid, size_gb):
            seen.add(mid.lower())
            found.append({
                "runtime": "lm_studio",
                "name": mid,
                "path": mid,
                "lms_id": mid,
                "size_gb": round(size_gb, 2),
            })

    # If LM Studio CLI returned models, use them directly (no filesystem duplicates)
    if found:
        return found

    # 2. Fallback: Filesystem search only if lms ls returned nothing
    home = Path.home()
    candidates = [
        home / ".cache" / "lm-studio" / "models",
        home / ".lmstudio" / "models",
        home / "AppData" / "Roaming" / "LMStudio" / "models",
    ]
    for base in candidates:
        if not base.exists():
            continue
        for gguf in base.rglob("*.gguf"):
            try:
                stem = gguf.stem
                if not is_valid_text_model(stem, 1.0):
                    continue
                key = stem.lower()
                if key in seen:
                    continue
                size_gb = round(gguf.stat().st_size / (1024 ** 3), 2)
                seen.add(key)
                found.append({
                    "runtime": "lm_studio",
                    "name": stem,
                    "path": str(gguf),
                    "lms_id": stem,
                    "size_gb": size_gb,
                })
            except OSError:
                continue

    return found


def find_ollama_models() -> list[dict]:
    stdout, _, _ = safe_run(["ollama", "list"])
    if not stdout or "NAME" not in stdout:
        return []
    found = []
    for line in stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        size_gb = 0.0
        for i, p in enumerate(parts):
            if p in ("GB", "MB") and i > 0:
                try:
                    val = float(parts[i - 1])
                    size_gb = val if p == "GB" else val / 1024
                except ValueError:
                    pass
                break

        if is_valid_text_model(name, size_gb):
            found.append({
                "runtime": "ollama",
                "name": name,
                "path": None,
                "lms_id": None,
                "size_gb": round(size_gb, 2),
            })
    return found


def find_all_models() -> list[dict]:
    return sorted(
        find_lmstudio_models() + find_ollama_models(),
        key=lambda m: m["size_gb"] or 999,
    )


def has_lmstudio_cli() -> bool:
    stdout, stderr, code = safe_run(["lms", "version"])
    blob = (stdout + stderr).lower()
    return code == 0 or "lm studio" in blob or "lms" in blob or "version" in blob


def has_ollama() -> bool:
    stdout, _, _ = safe_run(["ollama", "--version"])
    return "ollama version" in stdout.lower()
