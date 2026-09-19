<div align="center">

# 🏎️ InferBench

### The Ultimate AMD Local AI Backend Benchmarker (Vulkan vs HIP/ROCm)

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-orange)]()

</div>

---

## ❓ What is InferBench?

If you run local AI on an AMD GPU using Ollama or LM Studio, you constantly face the question: **"Should I use the Vulkan backend or the HIP/ROCm backend?"** 

The answer changes depending on your exact GPU, your driver version, and the specific model you are running. 

**InferBench** automates the answer. It scans your PC for LM Studio and Ollama models, temporarily isolates the server, runs a highly-controlled prompt generation race using Vulkan, forcefully clears your VRAM, runs the race again using HIP, and tells you exactly which one is faster.

### ✨ Features
* 🔍 **Auto-Discovery:** Automatically finds all installed Ollama and LM Studio models.
* 🧠 **Scientific Benchmarking:** Runs a warm-up inference (to populate VRAM/JIT), then executes 3 timed runs, taking the median average to eliminate outliers.
* 🧹 **Strict VRAM Management:** Forcefully unloads models between backend tests so VRAM leakage doesn't corrupt your results.
* 📊 **Community Telemetry:** (Opt-in) Sends anonymous benchmark results to a community database so we can map out the definitive AMD performance tier list.
* ⚙️ **Global Command:** Installs as a global system command (`inferbench run`) on its first launch.

---

## 🚀 Installation

Ensure you have Python 3.10+ installed.

Open your terminal (Command Prompt, PowerShell, or Bash) and run:

```bash
git clone https://github.com/xanpavle/inferbench.git
cd inferbench
pip install -e .
python -m inferbench run
```

On your first run, InferBench will ask to register itself globally. Once registered, you can type `inferbench` from any folder on your PC!

---

## 📋 Commands

| Command | What it does |
|---|---|
| `inferbench run` | Opens the interactive model picker and runs the deep benchmark |
| `inferbench run --quick` | Skips the 3-run median and just does 1 fast run per backend |
| `inferbench scan` | Scans your PC for GPUs, AI runtimes, and local `.gguf` models |
| `inferbench history` | View a history of your past benchmark results |
| `inferbench apply vulkan` | Edits your environment variables to set Vulkan as the default for Ollama |

---

## 📸 Example Output

```text
  Model: dolphin3-cyber-8b (3 runs per backend)

  Testing VULKAN...
    Unloading model...
    ✓ Speed: 97.78 t/s

  Testing HIP...
    Unloading model...
    ✓ Speed: 97.27 t/s

  ┌──────────────┬──────────────┬──────────────┬──────────────┐
  │   Backend    │  Prompt t/s  │   Gen t/s    │   TTFT (ms)  │
  ├──────────────┼──────────────┼──────────────┼──────────────┤
  │   Vulkan     │     97.78    │     97.78    │      0.0     │
  │   HIP/ROCm   │     97.27    │     97.27    │      0.0     │
  └──────────────┴──────────────┴──────────────┴──────────────┘

  🏆 Winner: VULKAN (+0.5%)
```

---

## 🤝 Pairing with ROCmFix
InferBench is the sister-project to [ROCmFix](https://github.com/xanpavle/rocmfix). 
If InferBench tells you that HIP is failing or running extremely slowly, use **ROCmFix** to automatically detect and apply the correct `HSA_OVERRIDE_GFX_VERSION` for your specific AMD graphics card.

---

## 📄 License
MIT License. Do whatever you want with it!