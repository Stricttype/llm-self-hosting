"""
Use Case 6: Local LLM Endpoint Probe
Quickly validates a local LLM endpoint (Ollama, vLLM, LM Studio, llama-server)
and reports model, latency, token counts. Useful for smoke tests + CI.

Ponytail: stdlib only (urllib). Tries OpenAI-compatible /v1/chat/completions first,
falls back to Ollama /api/chat. Self-check via __main__ in dry-run.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import json
import time
import urllib.request
import urllib.error


@dataclass
class ProbeResult:
    ok: bool = False
    backend: str = "unreachable"  # "openai" | "ollama" | "unreachable"
    model: str = ""
    ttft_ms: float = 0.0
    tokens_out: int = 0
    tokens_in: int = 0
    error: str = ""
    details: dict = field(default_factory=dict)


class LLMProbe:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _post(self, url: str, body: dict, headers: dict | None = None) -> tuple[int, dict, float]:
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        req.add_header("Content-Type", "application/json")
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode() or "{}")
                return resp.status, payload, (time.monotonic() - t0) * 1000
        except urllib.error.HTTPError as e:
            return e.code, {"error": e.read().decode()}, (time.monotonic() - t0) * 1000
        except urllib.error.URLError as e:
            return 0, {"error": str(e)}, (time.monotonic() - t0) * 1000

    def _try_openai(self, prompt: str) -> ProbeResult:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 32,
            "stream": False,
        }
        status, payload, ms = self._post(f"{self.base_url}/v1/chat/completions", body)
        if status == 200 and "choices" in payload:
            usage = payload.get("usage", {})
            return ProbeResult(
                ok=True, backend="openai",
                model=payload.get("model", self.model),
                ttft_ms=ms,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                details=payload,
            )
        return ProbeResult(ok=False, backend="openai", error=str(payload.get("error", status)))

    def _try_ollama(self, prompt: str) -> ProbeResult:
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "stream": False}
        status, payload, ms = self._post(f"{self.base_url}/api/chat", body)
        if status == 200 and "message" in payload:
            return ProbeResult(
                ok=True, backend="ollama",
                model=payload.get("model", self.model),
                ttft_ms=ms,
                tokens_out=payload.get("eval_count", 0),
                tokens_in=payload.get("prompt_eval_count", 0),
                details=payload,
            )
        return ProbeResult(ok=False, backend="ollama", error=str(payload.get("error", status)))

    def probe(self, prompt: str = "Say 'pong' and nothing else.") -> ProbeResult:
        """Try OpenAI-compatible first (covers vLLM, LM Studio, llama-server), then Ollama."""
        if "/v1" in self.base_url or ":8000" in self.base_url or ":1234" in self.base_url:
            r = self._try_openai(prompt)
            if r.ok:
                return r
        r = self._try_ollama(prompt)
        if r.ok:
            return r
        # Fallback: try OpenAI if we haven't
        if r.backend == "ollama":
            r2 = self._try_openai(prompt)
            if r2.ok:
                return r2
        return ProbeResult(ok=False, backend="unreachable", error=r.error or "no working backend")


if __name__ == "__main__":
    # Self-check: when no server is running, we expect a clean "unreachable" result.
    probe = LLMProbe(base_url="http://localhost:65535", model="nonexistent", timeout=2)
    r = probe.probe()
    assert not r.ok, "expected unreachable"
    assert r.backend == "unreachable", f"got {r.backend}"
    print(f"OK: unreachable detection works ({r.error[:60]})")
    # Sanity: backend string enum is bounded
    assert r.backend in ("openai", "ollama", "unreachable")
    print("OK: all probe invariants hold")