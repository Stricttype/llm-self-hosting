#!/usr/bin/env python3
"""
Local runner for the closed-loop workflow.
Walks agent/workflows/closed-loop.json, executes each step's command in dependency order,
emits per-stage events to events.jsonl (post-task hook equivalent per Claude v2),
and reports stage results to Ruflo (task_create / task_update) for tracking.

Ponytail: subprocess + JSON walking. No LLM calls, no API cost.
Ruflo agents are coordination metadata (who owns what stage); stage commands are local scripts.
"""

from __future__ import annotations
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
WORKFLOW = ROOT / "agent" / "workflows" / "closed-loop.json"
STATE = ROOT / "agent" / "state"
LOGS = ROOT / "agent" / "state" / "step_logs"
EVENTS = ROOT / "agent" / "events.jsonl"


def ruflo_call(tool: str, args: dict) -> dict:
    """Log Ruflo intent (no live MCP from subprocess — pi session can replay)."""
    log_path = STATE / "ruflo_intents.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps({"ts": time.time(), "tool": tool, "args": args}) + "\n")
    return {"logged": True, "tool": tool}


def emit_event(event: dict) -> None:
    """Append a structured event to events.jsonl. Per Claude v2: this is the post-task hook equivalent.
    Real hooks would call this from pi/Ruflo at task completion. Here we emit per-stage from run_loop.
    """
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a") as f:
        f.write(json.dumps(event) + "\n")


def execute_step(step: dict) -> tuple[int, str, float]:
    """Run a single step. Returns (returncode, stdout, duration_s)."""
    cmd = step["command"]
    if step.get("depends_on"):
        deps = step["depends_on"]
        for dep in deps:
            dep_result = STATE / "step_logs" / f"{dep}.json"
            if not dep_result.exists():
                return 1, "", 0.0
    # Force VALUE to use stub in CI/test context (ruflo CLI is slow with many events).
    if step["id"] == "value":
        cmd = cmd + " --no-mcp"
    print(f"[run_loop] >> step: {step['id']} ({step['cognitive_pattern']})")
    t0 = time.time()
    # Per-step timeout: VALUE stub is fast; live is slow.
    timeout_s = 180 if step["id"] == "value" else 60
    proc = subprocess.run(
        cmd, shell=True, cwd=str(ROOT),
        capture_output=True, text=True, timeout=timeout_s,
    )
    duration = time.time() - t0
    LOGS.mkdir(parents=True, exist_ok=True)
    log = {
        "step_id": step["id"],
        "cognitive_pattern": step["cognitive_pattern"],
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ts": t0,
        "duration_s": duration,
    }
    (LOGS / f"{step['id']}.json").write_text(json.dumps(log, indent=2))
    print(f"[run_loop]    rc={proc.returncode}  duration={duration:.2f}s  stdout={proc.stdout.strip()[:200]}")

    # Per-stage event (post-task hook equivalent)
    emit_event({
        "event_id": f"loop_{int(time.time())}_{step['id']}",
        "type": "stage_completion",
        "stage": step["id"],
        "cognitive_pattern": step["cognitive_pattern"],
        "outcome": "passed" if proc.returncode == 0 else "failed",
        "passed": proc.returncode == 0,
        "context": f"closed-loop stage {step['id']} ({step['cognitive_pattern']}) completed in {duration:.2f}s",
        "duration_s": duration,
        "ts": t0,
    })
    return proc.returncode, proc.stdout, duration


def main() -> int:
    workflow = json.loads(WORKFLOW.read_text())
    print(f"[run_loop] workflow: {workflow['name']} (strategy={workflow['strategy']})")

    STATE.mkdir(parents=True, exist_ok=True)
    ruflo_call("ruflo_task_create", {
        "title": f"closed-loop run @ {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "workflowId": workflow["id"],
    })
    emit_event({
        "event_id": f"loop_start_{int(time.time())}",
        "type": "loop_start",
        "outcome": "started",
        "passed": True,
        "context": f"closed-loop workflow {workflow['name']} started",
        "ts": time.time(),
    })

    steps = {s["id"]: s for s in workflow["steps"]}
    done: set[str] = set()
    failed: set[str] = set()

    # Topological execution
    while len(done) + len(failed) < len(steps):
        progressed = False
        for sid, step in steps.items():
            if sid in done or sid in failed:
                continue
            deps = step.get("depends_on", [])
            if any(d in failed for d in deps):
                print(f"[run_loop] skip {sid}: dependency failed")
                failed.add(sid)
                progressed = True
                continue
            if all(d in done for d in deps):
                rc, _, _ = execute_step(step)
                if rc == 0:
                    done.add(sid)
                else:
                    failed.add(sid)
                progressed = True
        if not progressed:
            break

    summary = {
        "workflow_id": workflow["id"],
        "ts": time.time(),
        "done": sorted(done),
        "failed": sorted(failed),
        "n_done": len(done),
        "n_failed": len(failed),
        "n_total": len(steps),
    }
    (STATE / "loop_summary.json").write_text(json.dumps(summary, indent=2))
    ruflo_call("ruflo_task_update", {
        "title": "closed-loop run complete",
        "summary": summary,
    })
    emit_event({
        "event_id": f"loop_complete_{int(time.time())}",
        "type": "loop_complete",
        "outcome": "passed" if not failed else "partial",
        "passed": not failed,
        "context": f"closed-loop completed: {len(done)}/{len(steps)} stages OK",
        "ts": summary["ts"],
    })
    print(f"\n[run_loop] {len(done)}/{len(steps)} stages OK, {len(failed)} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())