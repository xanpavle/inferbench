"""Core benchmarking engine with streaming TTFT capture and prompt length control."""

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


def _generate_prompt(target_tokens: int) -> str:
    """Generate a prompt of approximate token length for scaling tests."""
    if target_tokens <= 128:
        return BENCH_PROMPT
    base = (
        "Explain in extreme detail the following topic: quantum physics, general relativity, "
        "cellular biology, blockchain cryptography, and neural network architectures. "
    )
    return base * max(1, target_tokens // 30)


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
        try:
            subprocess.Popen(
                ["lms", "server", "start"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
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


def _stream_lmstudio(url: str, payload: dict, timeout: int = 600) -> tuple[float, float, int, bool]:
    """
    Returns (ttft_ms, total_time_s, completion_tokens, got_any_event).
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer lm-studio",
            "Accept": "text/event-stream",
        },
    )

    ttft_ms = 0.0
    start = time.time()
    total_tokens = 0
    first = False
    got_event = False
    usage_tokens = None

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        while True:
            line = resp.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded:
                continue
            if not decoded.startswith("data:"):
                continue
            payload_str = decoded[5:].strip()
            if payload_str == "[DONE]":
                break
            try:
                chunk = json.loads(payload_str)
            except Exception:
                continue

            got_event = True
            content = ""
            try:
                ch0 = (chunk.get("choices") or [{}])[0]
                delta = ch0.get("delta") or {}
                content = delta.get("content") or ""
                if not content and isinstance(ch0.get("message"), dict):
                    content = ch0["message"].get("content") or ""
            except Exception:
                content = ""

            if content and not first:
                ttft_ms = round((time.time() - start) * 1000.0, 2)
                first = True

            if content:
                # chunk-based count if usage missing
                total_tokens += 1

            usage = chunk.get("usage") or {}
            if usage.get("completion_tokens") is not None:
                try:
                    usage_tokens = int(usage["completion_tokens"])
                except (TypeError, ValueError):
                    pass

    if usage_tokens is not None and usage_tokens > 0:
        total_tokens = usage_tokens

    total_time = max(time.time() - start, 0.001)
    return ttft_ms, total_time, int(total_tokens), got_event


def _nonstream_lmstudio(payload: dict, timeout: int = 600) -> tuple[float, float, int]:
    """
    Fallback when SSE yields 0 tokens (common on some large/MoE models).
    Returns (ttft_ms_approx, total_time_s, completion_tokens).
    """
    body = dict(payload)
    body["stream"] = False
    t0 = time.time()
    data = _lms_api("POST", "/v1/chat/completions", body, timeout=timeout)
    elapsed = max(time.time() - t0, 0.001)

    usage = data.get("usage") or {}
    ctok = 0
    try:
        ctok = int(usage.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        ctok = 0

    if ctok <= 0:
        try:
            txt = data["choices"][0]["message"]["content"]
            ctok = max(len(str(txt).split()), 1)
        except Exception:
            ctok = 0

    # Approx TTFT when non-stream only (full wait)
    ttft_ms = round(elapsed * 1000.0, 2) if ctok > 0 else 0.0
    return ttft_ms, elapsed, ctok


def run_lmstudio_benchmark(
    model_id_or_path: str,
    model_name: str,
    backend: str,
    gpu_override: str | None,
    runs: int,
    progress_cb,
    prompt_len: int = 128,
) -> dict:
    results = []
    env = os.environ.copy()
    env["OLLAMA_GPU_BACKEND"] = backend
    if backend == "vulkan":
        env["GGML_VK_VISIBLE_DEVICES"] = "0"
    if gpu_override:
        env["HSA_OVERRIDE_GFX_VERSION"] = gpu_override

    keys_for_unload = [model_id_or_path, model_name]

    progress_cb("Ejecting all models from VRAM...")
    _unload_all_lms(env, keys_for_unload)

    if not _ensure_lms_server(env):
        return {"success": False, "error": "LM Studio server failed to start"}

    _unload_all_lms(env, keys_for_unload)

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

    progress_cb("Loading model into VRAM...")
    # Longer load timeout for large models (26B etc.)
    load_timeout = 300
    safe_run(["lms", "load", target_id, "-y"], env=env, timeout=load_timeout)

    # Bigger models need longer settle after load
    name_l = f"{target_id} {model_name}".lower()
    settle = 12 if any(x in name_l for x in ("26b", "27b", "30b", "32b", "70b")) else 4
    time.sleep(settle)

    prompt_text = _generate_prompt(prompt_len)
    prompt_payload = {
        "model": target_id,
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 128,
        "stream": True,
        "temperature": 0.0,
    }

    for i in range(runs + 1):
        if i == 0:
            progress_cb("Warm-up run...")
        else:
            progress_cb(f"Run {i}/{runs} (streaming TTFT)...")

        try:
            # Fixed: unpack all 4 return values from _stream_lmstudio
            ttft, total_time, tokens, got_event = _stream_lmstudio(
                "http://127.0.0.1:1234/v1/chat/completions",
                prompt_payload,
                timeout=600,
            )
            tok_s = round(tokens / total_time, 2) if total_time > 0 and tokens > 0 else 0.0

            # Fallback: non-stream if SSE empty (26B / MoE often)
            if tok_s <= 0:
                progress_cb("Stream empty — trying non-stream fallback...")
                ttft2, total_time2, tokens2 = _nonstream_lmstudio(prompt_payload, timeout=600)
                if tokens2 > 0:
                    ttft = ttft if ttft > 0 else ttft2
                    total_time = total_time2
                    tokens = tokens2
                    tok_s = round(tokens / total_time, 2) if total_time > 0 else 0.0

            if i > 0:
                if tok_s <= 0:
                    _unload_all_lms(env, keys_for_unload)
                    return {
                        "success": False,
                        "error": (
                            "Got 0 tokens from LM Studio (stream+fallback). "
                            "Load the model once in the LM Studio UI, ensure it fits VRAM, then retry."
                        ),
                    }
                results.append({"tok_s": tok_s, "ttft_ms": ttft})

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            if i > 0:
                _unload_all_lms(env, keys_for_unload)
                return {"success": False, "error": f"HTTP {e.code}: {body[:180]}"}
        except Exception as e:
            if i > 0:
                _unload_all_lms(env, keys_for_unload)
                return {"success": False, "error": str(e)}

    progress_cb("Unloading model...")
    _unload_all_lms(env, keys_for_unload)
    # optional: leave server running if user prefers; keep old stop behavior
    try:
        safe_run(["lms", "server", "stop"], env=env, timeout=15)
    except Exception:
        pass

    if not results:
        return {"success": False, "error": "No valid benchmark runs"}

    med_toks = round(_median([r["tok_s"] for r in results]), 2)
    med_ttft = round(_median([r["ttft_ms"] for r in results]), 2)

    if med_toks <= 0:
        return {"success": False, "error": "Median tok/s is 0 — not a valid result"}

    return {
        "success": True,
        "gen_tok_s": med_toks,
        "prompt_tok_s": med_toks,
        "ttft_ms": med_ttft,
        "runs": runs,
        "prompt_len": prompt_len,
    }


def run_ollama_benchmark(
    model_name: str,
    backend: str,
    gpu_override: str | None,
    runs: int,
    progress_cb,
    prompt_len: int = 128,
) -> dict:
    """Run Ollama benchmark with streaming TTFT capture."""
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
    prompt_text = _generate_prompt(prompt_len)
    prompt_payload = {"model": model_name, "prompt": prompt_text, "stream": True}

    for i in range(runs + 1):
        if i == 0:
            progress_cb("Warm-up run...")
        else:
            progress_cb(f"Run {i}/{runs} (streaming TTFT)...")

        try:
            data = json.dumps(prompt_payload).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
            )

            ttft_ms = 0.0
            start = time.time()
            total_tokens = 0
            first_token = False
            final_eval_count = 0
            final_eval_duration = 0
            tok_s = 0.0

            with urllib.request.urlopen(req, timeout=300) as resp:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    try:
                        chunk = json.loads(line.decode("utf-8", errors="replace"))
                    except Exception:
                        continue

                    if not first_token and chunk.get("response"):
                        ttft_ms = round((time.time() - start) * 1000, 2)
                        first_token = True

                    if chunk.get("response"):
                        total_tokens += 1

                    if chunk.get("done"):
                        final_eval_count = chunk.get("eval_count", total_tokens)
                        final_eval_duration = chunk.get("eval_duration", int((time.time() - start) * 1e9))
                        if chunk.get("prompt_eval_duration") and ttft_ms <= 0:
                            try:
                                ttft_ms = round(float(chunk["prompt_eval_duration"]) / 1e6, 2)
                            except Exception:
                                pass

            if final_eval_count and final_eval_duration:
                tok_s = round(final_eval_count / (final_eval_duration / 1e9), 2)
            else:
                elapsed = max(time.time() - start, 0.001)
                tok_s = round(total_tokens / elapsed, 2)

            if i > 0:
                if tok_s <= 0:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return {
                        "success": False,
                        "error": "Got 0 tokens from Ollama. Is the model pulled and GPU backend working?",
                    }
                results.append({"tok_s": tok_s, "ttft_ms": ttft_ms})
        except Exception as e:
            if i > 0:
                try:
                    proc.kill()
                except Exception:
                    pass
                return {"success": False, "error": str(e)}

    try:
        proc.kill()
    except Exception:
        pass

    if not results:
        return {"success": False, "error": "No valid benchmark runs"}

    med_toks = round(_median([r["tok_s"] for r in results]), 2)
    med_ttft = round(_median([r["ttft_ms"] for r in results]), 2)

    if med_toks <= 0:
        return {"success": False, "error": "Median tok/s is 0 — not a valid result"}

    return {
        "success": True,
        "gen_tok_s": med_toks,
        "prompt_tok_s": med_toks,
        "ttft_ms": med_ttft,
        "runs": runs,
        "prompt_len": prompt_len,
    }
