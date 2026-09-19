"""InferBench configuration and paths."""

import json
import uuid
from pathlib import Path

CONFIG_VERSION = 1

CONFIG_DIR = Path.home() / ".inferbench"
CONFIG_FILE = CONFIG_DIR / "config.json"
RESULTS_DIR = CONFIG_DIR / "results"
BACKENDS_DIR = CONFIG_DIR / "backends"
MODELS_DIR = CONFIG_DIR / "test_models"
OUTBOX_DIR = CONFIG_DIR / "outbox"

TELEMETRY_ENDPOINT = "https://rocmfix-data.onrender.com/submit"
TELEMETRY_TIMEOUT = 60

BENCH_PROMPT = "Write a detailed 100-word story about a robot learning to paint colors it has never seen before."
BENCH_WARM_UP_RUNS = 1
BENCH_TIMED_RUNS = 3
BENCH_MAX_TOKENS = 128


def ensure_dirs():
    """Create all config directories."""
    for d in [CONFIG_DIR, RESULTS_DIR, BACKENDS_DIR, MODELS_DIR, OUTBOX_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load user config or return defaults."""
    ensure_dirs()
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "config_version": CONFIG_VERSION,
        "user_id": str(uuid.uuid4()),
        "telemetry_enabled": None,
        "first_run": True,
    }


def save_config(cfg: dict):
    """Save user config."""
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
