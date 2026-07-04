#!/usr/bin/env python3
"""
Local runner for the closed-loop workflow.
Walks agent/workflows/closed-loop.json, executes each step's command in dependency order,
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


def ruflo_call(tool: str, args: dict) -> dict:
    """Call a Ruflo MCP tool via subprocess of claude -p? No — use the MCP gateway directly.
    But this script is called outside pi session; so use the ruFlo CLI if available, else log only.
    """
    # Fallback: log only, no live MCP call from this subprocess.
    log_path = STATE / "ruflo_intents.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.time(), "tool": tool, "args": args}
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return {"logged": True, "tool": tool}


def execute_step(step: dict) -> tuple[int, str, str]:
    """Run a single step. Returns (returncode, stdout, stderr)."""
    cmd = step["command"]
    if step.get("depends_on"):
        deps = step["depends_on"]
        for dep in deps:
            dep_result = STATE / "step_logs" / f"{dep}.json"
            if not dep_result.exists():
                return 1, "", f"missing dependency result: {dep}"
    print(f"[run_loop] >> step: {step['id']} ({step['cognitive_pattern']})")
    proc = subprocess.run(
        cmd, shell=True, cwd=str(ROOT),
        capture_output=True, text=True, timeout=60,
    )
    LOGS.mkdir(parents=True, exist_ok=True)
    log = {
        "step_id": step["id"],
        "cognitive_pattern": step["cognitive_pattern"],
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ts": time.time(),
    }
    (LOGS / f"{step['id']}.json").write_text(json.dumps(log, indent=2))
    print(f"[run_loop]    rc={proc.returncode}  stdout={proc.stdout.strip()[:200]}")
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    workflow = json.loads(WORKFLOW.read_text())
    print(f"[run_loop] workflow: {workflow['name']} (strategy={workflow['strategy']})")

    STATE.mkdir(parents=True, exist_ok=True)
    # Log the run start to Ruflo
    ruflo_call("ruflo_task_create", {
        "title": f"closed-loop run @ {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "workflowId": workflow["id"],
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
            break  # cycle or unsatisfiable deps

    summary = {
        "workflow_id": workflow["id"],
        "ts": time.time(),
        "done": sorted(done),
        "failed": sorted(failed),
        "ts_done": len(done),
        "n_failed": len(failed),
        "n_total": len(steps),
    }
    (STATE / "loop_summary.json").write_text(json.dumps(summary, indent=2))
    ruflo_call("ruflo_task_update", {
        "title": "closed-loop run complete",
        "summary": summary,
    })
    print(f"\n[run_loop] {len(done)}/{len(steps)} stages OK, {len(failed)} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())