"""Format results and report telemetry."""

import json
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone
from .config import RESULTS_DIR, OUTBOX_DIR, TELEMETRY_ENDPOINT, TELEMETRY_TIMEOUT, ensure_dirs, load_config


def format_results_table(vulkan: dict, hip: dict) -> str:
    """Format benchmark results into ASCII table."""
    lines = [
        "",
        "  ┌──────────────┬──────────────┬──────────────┬──────────────┐",
        "  │   Backend    │  Prompt t/s  │   Gen t/s    │   TTFT (ms)  │",
        "  ├──────────────┼──────────────┼──────────────┼──────────────┤",
    ]
    if vulkan.get("success"):
        lines.append(f"  │   Vulkan     │  {str(vulkan['prompt_tok_s']).center(11)}│  {str(vulkan['gen_tok_s']).center(11)}│  {str(vulkan['ttft_ms']).center(11)}│")
    else:
        lines.append("  │   Vulkan     │     FAIL     │     FAIL     │     FAIL     │")

    if hip.get("success"):
        lines.append(f"  │   HIP/ROCm   │  {str(hip['prompt_tok_s']).center(11)}│  {str(hip['gen_tok_s']).center(11)}│  {str(hip['ttft_ms']).center(11)}│")
    else:
        lines.append("  │   HIP/ROCm   │     FAIL     │     FAIL     │     FAIL     │")

    lines.append("  └──────────────┴──────────────┴──────────────┴──────────────┘")
    return "\n".join(lines)


def declare_winner(vulkan: dict, hip: dict) -> tuple[str, float]:
    """Return winner and speedup percentage."""
    vk_gen = vulkan.get("gen_tok_s", 0) if vulkan.get("success") else 0
    hp_gen = hip.get("gen_tok_s", 0) if hip.get("success") else 0

    if vk_gen == 0 and hp_gen == 0:
        return ("none", 0.0)
    if vk_gen >= hp_gen:
        pct = round(((vk_gen / hp_gen) - 1) * 100, 1) if hp_gen > 0 else 100.0
        return ("vulkan", pct)
    else:
        pct = round(((hp_gen / vk_gen) - 1) * 100, 1) if vk_gen > 0 else 100.0
        return ("hip", pct)


def save_result_local(payload: dict) -> str:
    """Save result JSON locally."""
    ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"bench_{ts}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def _queue_telemetry(payload: dict):
    ensure_dirs()
    fn = f"payload_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.json"
    (OUTBOX_DIR / fn).write_text(json.dumps(payload), encoding="utf-8")


def _send_telemetry(payload: dict) -> bool:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            TELEMETRY_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "InferBench/0.1.0"},
        )
        with urllib.request.urlopen(req, timeout=TELEMETRY_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def flush_outbox() -> tuple[int, int]:
    ensure_dirs()
    sent, failed = 0, 0
    for f in sorted(OUTBOX_DIR.glob("*.json")):
        try:
            if _send_telemetry(json.loads(f.read_text(encoding="utf-8"))):
                f.unlink()
                sent += 1
            else:
                failed += 1
        except Exception:
            f.unlink()
    return sent, failed


def build_telemetry_payload(scan: dict, model_info: dict, vulkan: dict, hip: dict) -> dict:
    cfg = load_config()
    winner, _ = declare_winner(vulkan, hip)
    gpu = scan["gpus"][0] if scan["gpus"] else {}
    return {
        "schema_version": 2,
        "user_id": cfg["user_id"],
        "rocmfix_version": "inferbench-0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "os": scan["os"],
        "shell": "cli",
        "gpu": {
            "name": gpu.get("name"),
            "pci_id": gpu.get("pci_id"),
            "driver_version": gpu.get("driver_version"),
        },
        "database": {"in_database": True, "override_recommended": None, "supported_native": True},
        "rocm_version": scan.get("hip", {}).get("version"),
        "benchmark": {
            "runtime": model_info.get("runtime", "unknown"),
            "model": model_info.get("name"),
            "vulkan_toks": vulkan.get("gen_tok_s", 0),
            "hip_toks": hip.get("gen_tok_s", 0),
            "winner": winner,
        },
    }


def send_result(payload: dict) -> bool:
    cfg = load_config()
    if not cfg.get("telemetry_enabled"):
        return False
    if not _send_telemetry(payload):
        _queue_telemetry(payload)
        return False
    flush_outbox()
    return True
