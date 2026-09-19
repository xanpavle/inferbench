"""Sanity tests for model_finder."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from inferbench.model_finder import find_all_models, has_ollama, has_lmstudio_cli


def test_find_all_models_shape():
    models = find_all_models()
    assert isinstance(models, list)
    for m in models:
        assert "runtime" in m
        assert "name" in m
        assert "size_gb" in m


def test_runtime_detection():
    assert isinstance(has_ollama(), bool)
    assert isinstance(has_lmstudio_cli(), bool)


if __name__ == "__main__":
    print(f"Ollama installed: {has_ollama()}")
    print(f"LM Studio CLI installed: {has_lmstudio_cli()}")
    models = find_all_models()
    print(f"\nFound {len(models)} models:")
    for m in models[:5]:
        print(f"  - {m['name']} ({m['size_gb']} GB) [{m['runtime']}]")
