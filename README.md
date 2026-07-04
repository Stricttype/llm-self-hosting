# llm-self-hosting — Use Cases

Executable, tested Python scripts that operationalize 2026 LLM self-hosting patterns.

Built from deep research stored in [`vault/projects/llm-self-hosting/`](file:///Users/kayaking/Documents/Obsidian%20Vault/projects/llm-self-hosting/) and the Ruflo memory/ReasoningBank (8 memory entries + 4 patterns under namespace `llm-self-hosting`).

## Use Cases

| File | Purpose | Self-check |
|------|---------|------------|
| `vllm_config.py` | Generate `vllm serve` command for goal (throughput/latency/memory/long-context/multi-lora) | 5 presets round-trip |
| `hardware_sizer.py` | Given model size + quant + concurrency → VRAM + GPU recommendation | 4 sizing cases |
| `cost_calculator.py` | Self-host vs API cost crossover for monthly token volume | 3 hosts × 3 utils × 4 volumes + crossover assertion |
| `prompt_guard.py` | Layered prompt-injection detection (rules + optional Llama Prompt Guard 2) | 5/5 rule cases |
| `lora_manager.py` | Multi-LoRA hot-swap lifecycle against vLLM (`/v1/load_lora_adapter`) | dry-run load/unload/health |
| `llm_probe.py` | Smoke-test any local LLM endpoint (vLLM/Ollama/LM Studio/llama-server) | unreachable detection |

## Run all tests

```bash
python3 tests/run_all.py
```

Expected output:
```
Running 6 use-case self-checks:
  ✓ cost_calculator       OK: cost calc handles 3 hosts × 3 utils × 4 volumes + crossover assertion
  ✓ hardware_sizer        OK: all sizing cases pass
  ✓ llm_probe             OK: all probe invariants hold
  ✓ lora_manager          OK: dry-run LoRA manager: load/unload/health all pass
  ✓ prompt_guard          OK: 5/5 rule-based cases detected correctly
  ✓ vllm_config           OK: 6 vLLM presets generate cleanly

6/6 passed
```

## Quick examples

```bash
# Generate a max-throughput vLLM command
python3 use-cases/vllm_config.py

# Size hardware for Llama 3.3 70B at Q4 with 4 concurrent users
python3 -c "from use_cases.hardware_sizer import size_model; print(size_model(70, 'Q4_K_M', seq_len=8192, concurrency=4))"

# Compare self-host vs API for 200M tokens/month
python3 -c "from use_cases.cost_calculator import recommend; print(recommend(200_000_000))"

# Probe local Ollama
python3 -c "from use_cases.llm_probe import LLMProbe; print(LLMProbe('http://localhost:11434', 'llama3.2').probe())"
```

## Dependencies

- **Stdlib only** for all 6 scripts (deliberate — these are run-anywhere utilities).
- Optional: `transformers` + `torch` for `prompt_guard.py` to load Llama Prompt Guard 2 86M (auto-degrades to rule-only if missing).

## Provenance

Patterns extracted from 4 parallel web searches (2026-07-04) on:

1. Hardware & engines: GPU landscape, quantization formats, vLLM/SGLang/TRT-LLM benchmarks
2. Tuning patterns: PagedAttention, FP8 KV cache, prefix caching, speculative decoding, LoRA
3. Cost/safety/deploy: Pricing math, multi-tenant isolation, Llama Firewall, K8s Helm
4. Local/edge: Apple Silicon, Ollama vs LM Studio vs Jan, mobile frameworks, open-weights

Stored to:
- Vault reports: `~/Documents/Obsidian Vault/projects/llm-self-hosting/reports/0[1-4]-*.md`
- Ruflo memory DB: namespace `llm-self-hosting`, 8 entries
- Ruflo ReasoningBank: 4 high-confidence patterns
- Hive-mind: `hive-1783153926448-kgwru7` (mesh topology, raft consensus)