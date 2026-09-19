# InferBench Privacy

## What is collected (only if you opt in)

- GPU name and PCI ID
- Driver / OS / shell
- Model name and approximate size
- Benchmark results (Vulkan tok/s, HIP tok/s, winner)
- Anonymous random user ID (stored only on your PC)
- InferBench version and timestamp

## What is NEVER collected

- Your name, email, or username
- IP address (stripped by hosting)
- File paths on your disk
- Prompt text beyond the fixed built-in bench prompt
- Chat history or model weights

## Opt out

Delete `~/.inferbench/config.json` or set telemetry off on first run by choosing **N**.

## Where data goes

Same community collector used by ROCmFix:  
`https://rocmfix-data.onrender.com/submit` → private Supabase table for AMD performance research.