"""Core benchmarking engine with VRAM cleanup and duplicate instance prevention."""

import os
import json
import time
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from .config import BENCH_PROMPT
from .detector import detect_os
from .utils import safe_run


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _lms_api(method: str, path: str, body: dict | None = None, timeout: int = 120):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:1234{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer lm-studio",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _unload_all_lms(env: dict, model_keys: list[str] | None = None):
    """Forcefully eject all models from LM Studio VRAM."""
    cmds = [
        ["lms", "unload", "--all"],
        ["lms", "unload", "-a"],
        ["lms", "unload"],
    ]
    for k in model_keys or []:
        if k:
            cmds.insert(0, ["lms", "unload", str(k)])

    for cmd in cmds:
        safe_run(cmd, env=env, timeout=15)
    time.sleep(2)


def _ensure_lms_server(env: dict) -> bool:
    safe_run(["lms", "server", "stop"], env=env, timeout=15)
    time.sleep(1)
    flags = 0x08000000 if detect_os() == "windows" else 0
    try:
        subprocess.Popen(
            ["lms", "server", "start"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception:
        pass

    for _ in range(20):
        try:
            _lms_api("GET", "/v1/models", timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False


def run_lmstudio_benchmark(
    model_id_or_path: str,
    model_name: str,
    backend: str,
    gpu_override: str | None,
    runs: int,
    progress_cb,
) -> dict:
    results = []
    env = os.environ.copy()
    env["OLLAMA_GPU_BACKEND"] = backend
    if backend == "vulkan":
        env["GGML_VK_VISIBLE_DEVICES"] = "0"
    if gpu_override:
        env["HSA_OVERRIDE_GFX_VERSION"] = gpu_override

    keys_for_unload = [model_id_or_path, model_name]

    # 1. Unload any existing models and restart server with clean env
    progress_cb("Ejecting all models from VRAM...")
    _unload_all_lms(env, keys_for_unload)

    if not _ensure_lms_server(env):
        return {"success": False, "error": "LM Studio server failed to start"}

    _unload_all_lms(env, keys_for_unload)

    # 2. Resolve model ID
    target_id = model_name
    try:
        data = _lms_api("GET", "/v1/models", timeout=5)
        for m in (data.get("data") or []):
            mid = str(m.get("id", ""))
            if model_name.lower() in mid.lower() or Path(str(model_id_or_path)).stem.lower() in mid.lower():
                target_id = mid
                break
    except Exception:
        pass

    keys_for_unload.append(target_id)

    # 3. Explicitly load model once
    progress_cb("Loading model into VRAM...")
    safe_run(["lms", "load", target_id, "-y"], env=env, timeout=120)
    time.sleep(3)

    prompt_payload = {
        "model": target_id,
        "messages": [{"role": "user", "content": BENCH_PROMPT}],
        "max_tokens": 128,
        "stream": False,
        "temperature": 0.0,
    }

    # 4. Perform benchmark runs
    for i in range(runs + 1):
        if i == 0:
            progress_cb("Warm-up run...")
        else:
            progress_cb(f"Run {i}/{runs}...")

        try:
            start = time.time()
            res_data = _lms_api("POST", "/v1/chat/completions", prompt_payload, timeout=180)
            elapsed = max(time.time() - start, 0.001)

            usage = res_data.get("usage") or {}
            toks = usage.get("completion_tokens") or usage.get("total_tokens") or 64
            tok_s = round(toks / elapsed, 2)

            if i > 0:
                results.append(tok_s)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            if i > 0:
                _unload_all_lms(env, keys_for_unload)
                return {"success": False, "error": f"HTTP {e.code}: {body[:100]}"}
        except Exception as e:
            if i > 0:
                _unload_all_lms(env, keys_for_unload)
                return {"success": False, "error": str(e)}

    # 5. Clean up VRAM completely after backend run
    progress_cb("Unloading model...")
    _unload_all_lms(env, keys_for_unload)

    if not results:
        return {"success": False, "error": "No valid benchmark runs"}

    med_toks = round(_median(results), 2)
    return {
        "success": True,
        "gen_tok_s": med_toks,
        "prompt_tok_s": med_toks,
        "ttft_ms": 0.0,
        "runs": runs,
    }


def run_ollama_benchmark(model_name: str, backend: str, gpu_override: str | None, runs: int, progress_cb) -> dict:
    """Run Ollama benchmark."""
    results = []
    env = os.environ.copy()
    env["OLLAMA_GPU_BACKEND"] = backend
    if gpu_override:
        env["HSA_OVERRIDE_GFX_VERSION"] = gpu_override

    if detect_os() == "windows":
        safe_run(["taskkill", "/F", "/IM", "ollama_app.exe"], timeout=5)
        safe_run(["taskkill", "/F", "/IM", "ollama.exe"], timeout=5)
    else:
        safe_run(["pkill", "-9", "ollama"], timeout=5)
    time.sleep(1)

    try:
        proc = subprocess.Popen(
            ["ollama", "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=0x08000000 if detect_os() == "windows" else 0,
        )
    except Exception as e:
        return {"success": False, "error": f"Failed to launch Ollama: {e}"}

    time.sleep(4)
    prompt_payload = {"model": model_name, "prompt": BENCH_PROMPT, "stream": False}

    for i in range(runs + 1):
        if i == 0:
            progress_cb("Warm-up run...")
        else:
            progress_cb(f"Run {i}/{runs}...")

        try:
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps(prompt_payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                tok_s = round(data.get("eval_count", 0) / (data.get("eval_duration", 1) / 1e9), 2)
                ttft_ms = round(data.get("prompt_eval_duration", 0) / 1e6, 2)
                if i > 0:
                    results.append((tok_s, ttft_ms))
        except Exception as e:
            if i > 0:
                try: proc.kill()
                except Exception: pass
                return {"success": False, "error": str(e)}

    try: proc.kill()
    except Exception: pass

    if not results:
        return {"success": False, "error": "No valid benchmark runs"}

    med_toks = round(_median([r[0] for r in results]), 2)
    med_ttft = round(_median([r[1] for r in results]), 2)
    return {
        "success": True,
        "gen_tok_s": med_toks,
        "prompt_tok_s": med_toks,
        "ttft_ms": med_ttft,
        "runs": runs,
    }
