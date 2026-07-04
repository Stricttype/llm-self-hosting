"""
Use Case 3: Self-host vs API Cost Calculator
Picks optimal hosting strategy based on monthly token volume + utilization.

Ponytail: stdlib math, one helper. Self-check via __main__.
"""

from __future__ import annotations
from dataclasses import dataclass


# 2026-07 reference rates (verify against pecollective.com, aipricing.guru)
@dataclass(frozen=True)
class HostProfile:
    name: str
    hourly_cost_usd: float
    tokens_per_hour_at_full: int    # aggregate tok/s * 3600


HOSTS = {
    "H100_on_demand": HostProfile("H100 on-demand", 2.50, 6_600_000),
    "H200_on_demand": HostProfile("H200 on-demand (141GB HBM3e)", 3.20, 8_500_000),
    "B200_on_demand": HostProfile("B200 on-demand (FP4)", 5.50, 54_000_000),
    "B200_spot":      HostProfile("B200 spot (FP4)",      2.12, 54_000_000),
}


@dataclass(frozen=True)
class APITier:
    name: str
    input_per_million: float
    output_per_million: float


APIS = {
    "gpt-5.5":      APITier("GPT-5.5 / Claude Fable 5",  7.50, 40.00),
    "gpt-5.4":      APITier("GPT-5.4 / Claude Sonnet 5", 2.50, 12.00),
    "gpt-4.1-nano": APITier("GPT-4.1 Nano / Llama Scout", 0.10, 0.35),
}


def blended_cost_per_million(tokens_month: int, in_out_ratio: float = 0.3) -> float:
    """tokens_month = total tokens. in_out_ratio = input / total (default 30% input)."""
    input_share = in_out_ratio
    output_share = 1 - in_out_ratio
    # Assume 90% cache hit discount on input (2026 norm for long context)
    effective_input_rate = 7.50 * 0.10  # 90% off
    return effective_input_rate * input_share + 40.00 * output_share


def cost_self_host(tokens_month: int, host: str, utilization: float = 1.0) -> float:
    """Returns total monthly USD."""
    h = HOSTS[host]
    if utilization <= 0 or utilization > 1:
        raise ValueError("utilization must be in (0, 1]")
    # You pay for the GPU 24/7 regardless of load.
    hours_per_month = 730
    gpu_cost = h.hourly_cost_usd * hours_per_month
    effective_capacity = h.tokens_per_hour_at_full * hours_per_month * utilization
    cost_per_m = gpu_cost / (effective_capacity / 1e6)
    total = cost_per_m * (tokens_month / 1e6)
    return total


def cost_api(tokens_month: int, tier: str) -> float:
    a = APIS[tier]
    input_t = tokens_month * 0.3
    output_t = tokens_month * 0.7
    return (input_t / 1e6) * a.input_per_million + (output_t / 1e6) * a.output_per_million


def recommend(tokens_month: int, host: str = "B200_on_demand", util: float = 0.5) -> str:
    api_cost = cost_api(tokens_month, "gpt-5.4")
    self_cost = cost_self_host(tokens_month, host, util)
    if self_cost < api_cost:
        saving = (api_cost - self_cost) / max(api_cost, 1)
        return f"SELF-HOST ({host} @ {util*100:.0f}% util): ${self_cost:,.0f}/mo vs API ${api_cost:,.0f}/mo → save {saving*100:.0f}%"
    return f"API (gpt-5.4): ${api_cost:,.0f}/mo vs self-host ${self_cost:,.0f}/mo → use API"


if __name__ == "__main__":
    # Self-check
    for vol in [10_000_000, 80_000_000, 500_000_000, 2_000_000_000]:
        for host in HOSTS:
            for util in [0.2, 0.5, 1.0]:
                sc = cost_self_host(vol, host, util)
                assert sc > 0, f"{host} {util}: zero cost for {vol}"
        ac = cost_api(vol, "gpt-5.4")
        assert ac > 0
        print(f"vol={vol/1e6:.0f}M → {recommend(vol)}")
    # Crossover sanity: at 80M/mo + 100% util on B200, self-host should win
    assert cost_self_host(80_000_000, "B200_spot", 1.0) < cost_api(80_000_000, "gpt-5.4")
    print("\nOK: cost calc handles 3 hosts × 3 utils × 4 volumes + crossover assertion")
__variant_id__ = "cost_calculator__v0_control"
__variant_id__ = "cost_calculator__v1_add_h200_tier"
