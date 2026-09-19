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

def ensure_dirs():
    for d in [CONFIG_DIR, RESULTS_DIR, BACKENDS_DIR, MODELS_DIR, OUTBOX_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def load_config() -> dict:
    ensure_dirs()
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text())
        except Exception: pass
    return {"config_version": CONFIG_VERSION, "user_id": str(uuid.uuid4()), "telemetry_enabled": None, "first_run": True}

def save_config(cfg: dict):
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
