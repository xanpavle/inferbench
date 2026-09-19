"""InferBench CLI entry point."""

import argparse
import sys
from pathlib import Path
from . import __version__
from .config import load_config, save_config, RESULTS_DIR, ensure_dirs
from .detector import full_scan
from .model_finder import find_all_models, has_lmstudio_cli, has_ollama
from .benchmarker import run_lmstudio_benchmark, run_ollama_benchmark
from .reporter import (
    format_results_table, declare_winner, save_result_local,
    build_telemetry_payload, send_result
)
from .utils import C, enable_ansi, install_globally
from .integrations import apply_backend_to_ollama


def print_header():
    print(f"{C.BOLD}{C.BLUE}\n  ╔══════════════════════════════════════════╗")
    print(f"  ║          InferBench v{__version__.ljust(20)}║")
    print("  ║   Deep Vulkan vs HIP Backend Benchmarker ║")
    print(f"  ╚══════════════════════════════════════════╝\n{C.RESET}")


def prompt_telemetry_optin() -> bool:
    print(f"  {C.BOLD}{C.CYAN}📊 Share benchmark results?{C.RESET}")
    print("  Share anonymous performance data to build the community database.")
    while True:
        try:
            ans = input(f"  Share data? [Y/n]: ").strip().lower()
        except Exception:
            return False
        if ans in ("y", ""): return True
        if ans == "n": return False


def cmd_scan(args):
    print_header()
    scan = full_scan()
    print(f"  {C.BOLD}OS:{C.RESET} {scan['os']}")
    print(f"  {C.BOLD}GPUs:{C.RESET}")
    for g in scan["gpus"]:
        print(f"    {C.GREEN}✓{C.RESET} {g['name']} (PCI {g['pci_id']})")
    print(f"\n  {C.BOLD}AI Runtimes:{C.RESET}")
    print(f"    {'✓ Ollama' if has_ollama() else '✗ Ollama'}")
    print(f"    {'✓ LM Studio' if has_lmstudio_cli() else '✗ LM Studio'}")

    models = find_all_models()
    print(f"\n  {C.BOLD}Models Found ({len(models)}):{C.RESET}")
    for m in models[:10]:
        print(f"    - {m['name']} ({m['size_gb']} GB) [{m['runtime']}]")
    print()


def cmd_run(args):
    print_header()
    cfg = load_config()

    # First-run prompts
    if cfg.get("first_run"):
        if not cfg.get("installed_globally"):
            if install_globally():
                cfg["installed_globally"] = True

        if cfg.get("telemetry_enabled") is None:
            cfg["telemetry_enabled"] = prompt_telemetry_optin()

        cfg["first_run"] = False
        save_config(cfg)

    scan = full_scan()
    if not scan["gpus"]:
        print(f"  {C.RED}✗ No AMD GPU detected. Aborting.{C.RESET}")
        return

    gpu = scan["gpus"][0]
    gpu_override = "11.0.0" if gpu["pci_id"] in ["7470", "7471", "7480", "7483"] else None

    models = find_all_models()
    if not models:
        print(f"  {C.YELLOW}No valid LLM models found in LM Studio or Ollama.{C.RESET}")
        return

    print(f"  {C.BOLD}Select a model to benchmark:{C.RESET}")
    for i, m in enumerate(models[:15], 1):
        print(f"    [{i}] {m['name']} ({m['size_gb']} GB) - {m['runtime']}")
    try:
        sel = int(input("\n  > ").strip())
        model_info = models[sel - 1]
    except Exception:
        return

    runs = 1 if args.quick else 3
    print(f"\n  {C.BOLD}Model:{C.RESET} {model_info['name']} ({runs} runs per backend)")

    results = {}
    for backend in ["vulkan", "hip"]:
        print(f"\n  {C.BOLD}Testing {backend.upper()}...{C.RESET}")

        def _prog(msg):
            sys.stdout.write(f"\r    {C.GRAY}{msg}{C.RESET}".ljust(60))
            sys.stdout.flush()

        if model_info["runtime"] == "lm_studio":
            r = run_lmstudio_benchmark(
                model_info.get("path") or model_info["name"],
                model_info["name"],
                backend,
                gpu_override,
                runs,
                _prog,
            )
        else:
            r = run_ollama_benchmark(model_info["name"], backend, gpu_override, runs, _prog)

        print()
        results[backend] = r
        if r.get("success"):
            print(f"    {C.GREEN}✓ Speed: {r['gen_tok_s']} t/s{C.RESET}")
        else:
            print(f"    {C.RED}✗ Failed: {r.get('error', 'unknown')}{C.RESET}")

    print(format_results_table(results.get("vulkan", {}), results.get("hip", {})))
    winner, pct = declare_winner(results.get("vulkan", {}), results.get("hip", {}))
    if winner != "none":
        print(f"\n  🏆 {C.GREEN}Winner: {winner.upper()} (+{pct}%){C.RESET}\n")

        payload = build_telemetry_payload(scan, model_info, results.get("vulkan", {}), results.get("hip", {}))
        save_result_local(payload)

        if cfg.get("telemetry_enabled"):
            print(f"  {C.GRAY}Sending results to database...{C.RESET}")
            send_result(payload)
            print(f"  {C.GREEN}✓ Sent!{C.RESET}\n")


def cmd_history(args):
    print_header()
    ensure_dirs()
    files = sorted(RESULTS_DIR.glob("bench_*.json"), reverse=True)
    if not files:
        print(f"  {C.YELLOW}No benchmark history yet. Run 'python -m inferbench run' first.{C.RESET}\n")
        return
    print(f"  {C.BOLD}Recent benchmarks ({len(files)}):{C.RESET}\n")
    for f in files[:20]:
        try:
            import json
            data = json.loads(f.read_text(encoding="utf-8"))
            b = data.get("benchmark", {})
            gpu = data.get("gpu", {})
            print(f"  {C.CYAN}{f.stem}{C.RESET}")
            print(f"    GPU: {gpu.get('name', '?')}")
            print(f"    Model: {b.get('model', '?')}")
            print(f"    Vulkan: {b.get('vulkan_toks', 0)} t/s | HIP: {b.get('hip_toks', 0)} t/s → {str(b.get('winner', '?')).upper()}")
            print()
        except Exception:
            continue


def main():
    enable_ansi()
    parser = argparse.ArgumentParser(prog="inferbench")
    parser.add_argument("--version", action="version", version=f"InferBench {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("scan")
    run_p = sub.add_parser("run")
    run_p.add_argument("--quick", action="store_true")

    sub.add_parser("history")
    sub.add_parser("install")

    apply_p = sub.add_parser("apply")
    apply_p.add_argument("backend", choices=["vulkan", "hip"])

    args = parser.parse_args()

    if args.command == "scan": cmd_scan(args)
    elif args.command == "run": cmd_run(args)
    elif args.command == "history": cmd_history(args)
    elif args.command == "install": install_globally()
    elif args.command == "apply":
        res = apply_backend_to_ollama(args.backend)
        print(res.get("message") or res.get("error"))
    else:
        print_header()
        parser.print_help()


if __name__ == "__main__":
    main()
