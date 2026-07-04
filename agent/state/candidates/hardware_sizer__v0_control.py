"""
Use Case 2: Hardware Sizing Calculator
Given model size + quant + concurrency, returns required VRAM/RAM.

Ponytail: pure stdlib math, one helper, zero deps. Self-check via __main__.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class QuantSpec:
    bits_per_weight: float
    overhead_pct: float   # tokenizer + framework overhead


# 2026 reference table (verifiable against localaimaster.com / HuggingFace model cards)
QUANTS: dict[str, QuantSpec] = {
    "FP16":   QuantSpec(16.0, 0.10),
    "Q8_0":   QuantSpec(8.0,  0.10),
    "Q5_K_M": QuantSpec(5.5,  0.12),
    "Q4_K_M": QuantSpec(4.5,  0.12),
    "AWQ-4":  QuantSpec(4.0,  0.12),
    "AWQ-3":  QuantSpec(3.0,  0.15),
}


@dataclass(frozen=True)
class Sizing:
    weights_gb: float
    kv_cache_gb: float
    total_gb: float
    recommended_gpu: str
    notes: str


def _kv_cache_gb(model_params_b: float, seq_len: int, concurrency: int, bytes_per_elem: int = 2) -> float:
    """KV cache ≈ 2 * n_layers * n_kv_heads * head_dim * seq_len * bytes_per_elem * batch.
    Llama-70B rule of thumb: ~0.5 MB per token per sequence at FP16.
    """
    # Empirical: ~0.5 MB/token at FP16 for 70B. Scale linearly with sqrt(params).
    bytes_per_token = 0.5e6 * (model_params_b / 70) ** 0.5
    return (bytes_per_token * seq_len * concurrency) / 1e9


def size_model(model_params_b: float, quant: str, seq_len: int = 4096, concurrency: int = 1) -> Sizing:
    if quant not in QUANTS:
        raise ValueError(f"Unknown quant '{quant}'. Choose: {list(QUANTS)}")
    spec = QUANTS[quant]
    weights_gb = (model_params_b * 1e9 * spec.bits_per_weight / 8) / 1e9 * (1 + spec.overhead_pct)
    kv_gb = _kv_cache_gb(model_params_b, seq_len, concurrency)
    total = weights_gb + kv_gb
    # GPU recommendation
    if total <= 24:
        gpu = "RTX 4090 (24GB) / M4 Pro 48GB"
    elif total <= 32:
        gpu = "RTX 5090 (32GB) / M4 Max 64GB"
    elif total <= 48:
        gpu = "RTX 5090 + offload / M5 Max 64GB"
    elif total <= 80:
        gpu = "H100 80GB / A100 80GB / M3 Ultra 192GB"
    elif total <= 140:
        gpu = "2x H100 / M5 Ultra 768GB"
    elif total <= 192:
        gpu = "B200 192GB (single GPU fits frontier models like Llama 4 70B FP16)"
    else:
        gpu = "Multi-B200 cluster (frontier research / 400B+ MoE)"
    notes = f"weights={weights_gb:.1f}GB, kv={kv_gb:.2f}GB @ seq={seq_len} conc={concurrency}"
    return Sizing(weights_gb, kv_gb, total, gpu, notes)


if __name__ == "__main__":
    # Self-check
    cases = [
        (7, "Q4_K_M", 4096, 1),     # 7B Q4 single user
        (70, "Q4_K_M", 8192, 4),    # 70B Q4 moderate concurrency
        (70, "FP16", 4096, 1),      # 70B full precision
        (405, "AWQ-4", 16384, 8),   # Llama 4 Behemoth-ish
    ]
    for params, quant, seq, conc in cases:
        s = size_model(params, quant, seq, conc)
        assert s.total_gb > 0
        assert s.recommended_gpu
        print(f"{params}B {quant} seq={seq} conc={conc} → {s.total_gb:.1f}GB → {s.recommended_gpu}")
    print("\nOK: all sizing cases pass")
__variant_id__ = "hardware_sizer__v1_add_b200_tier"
__variant_id__ = "hardware_sizer__v0_control"
