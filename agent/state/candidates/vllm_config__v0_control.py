"""
Use Case 1: vLLM Config Generator
Picks optimal vLLM flags for a given goal (throughput vs latency vs memory).
Ponytail: dict of presets, one helper, zero deps. Self-check via __main__.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class VLLMConfig:
    goal: str
    flags: tuple[str, ...]
    notes: str


PRESETS: dict[str, VLLMConfig] = {
    "max_throughput": VLLMConfig(
        goal="max_throughput",
        flags=(
            "--max-num-batched-tokens 16384",
            "--kv-cache-dtype fp8",
            "--gpu-memory-utilization 0.95",
            "--enable-chunked-prefill",
            "--max-num-seqs 512",
        ),
        notes="H100/B200 sweet spot. +EAGLE-3 if batch<8: --speculative-config eagle3.",
    ),
    "lowest_latency": VLLMConfig(
        goal="lowest_latency",
        flags=(
            "--max-num-batched-tokens 2048",
            "--enable-chunked-prefill",
            "--max-num-partial-prefills 1",
            "--long-prefill-token-threshold 4096",
            "--max-long-partial-prefills 1",
            "--kv-cache-dtype fp8",
        ),
        notes="Penalize throughput for p99 TTFT. Disable speculative decoding.",
    ),
    "memory_constrained": VLLMConfig(
        goal="memory_constrained",
        flags=(
            "--gpu-memory-utilization 0.85",
            "--kv-cache-dtype fp8",
            "--quantization awq",
            "--max-model-len 8192",
        ),
        notes="AWQ 4-bit + FP8 KV cache. For 24-32GB consumer GPUs.",
    ),
    "long_context": VLLMConfig(
        goal="long_context",
        flags=(
            "--max-model-len 131072",
            "--enable-chunked-prefill",
            "--kv-cache-dtype fp8",
            "--kv-transfer-config '{\"kv_connector\":\"NixlConnector\"}'",
        ),
        notes="Disaggregated prefill/decode. Requires vLLM >= 0.7 + RDMA network.",
    ),
    "multi_lora": VLLMConfig(
        goal="multi_lora",
        flags=(
            "--enable-lora",
            "--max-loras 4",
            "--max-lora-rank 64",
            "--max-cpu-loras 32",
            "--enable-prefix-caching",
        ),
        notes="Set env VLLM_ALLOW_RUNTIME_LORA_UPDATING=True for hot-swap API.",
    ),
    "blackwell_fp4": VLLMConfig(
        goal="blackwell_fp4",
        flags=(
            "--max-num-batched-tokens 32768",
            "--kv-cache-dtype fp4",
            "--gpu-memory-utilization 0.95",
            "--enable-chunked-prefill",
        ),
        notes="B200/Blackwell-only. FP4 KV cache + 32K batched tokens. 2-3x throughput vs FP8.",
    ),
}


def generate(goal: str, model: str, port: int = 8000) -> str:
    """Return the vllm serve command for a given goal."""
    if goal not in PRESETS:
        raise ValueError(f"Unknown goal '{goal}'. Choose from: {list(PRESETS)}")
    preset = PRESETS[goal]
    flag_str = " ".join(preset.flags)
    return (
        f"vllm serve {model} \\\n  "
        + " \\\n  ".join(preset.flags)
        + f" \\\n  --port {port}"
    )


if __name__ == "__main__":
    # Self-check: every preset round-trips.
    for goal in PRESETS:
        cmd = generate(goal, "meta-llama/Llama-3.3-70B-Instruct")
        assert "vllm serve" in cmd, f"missing serve in {goal}"
        assert cmd.count("\\") >= 2, f"bad flag layout in {goal}"
    print(f"OK: {len(PRESETS)} vLLM presets generate cleanly")
    print("\n--- Example: max_throughput ---")
    print(generate("max_throughput", "meta-llama/Llama-3.3-70B-Instruct"))
__variant_id__ = "vllm_config__v1_add_fp4_preset"
__variant_id__ = "vllm_config__v0_control"
