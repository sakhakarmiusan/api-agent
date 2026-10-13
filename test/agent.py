"""API test agent.

    python agent.py plan      # make out/plan.md, then ask: Enter = execute, q = quit
    python agent.py execute   # run the plan one test at a time, write + run pytest, report
"""
import json
import logging
import sys
import time
import warnings

warnings.filterwarnings("ignore")  # hide Python 3.9 / LibreSSL noise
logging.getLogger("google_genai").setLevel(logging.ERROR)  # hide thought_signature notice

import config
import llm
import safety
import tools


def read(name):
    p = config.HERE / name
    return p.read_text() if p.exists() else ""


def build_prompt(mode, history):
    parts = [read(f"prompt_{mode}.txt"), "# API\n" + read("api.md"), "# RULES\n" + read("rules.md")]
    if mode == "execute":
        parts.append("# PLAN (current state)\n" + read("out/plan.md"))
    parts.append("# HISTORY\n" + ("\n".join(json.dumps(h) for h in history) or "(empty, this is turn 1)"))
    parts.append("Reply with ONE JSON object: {\"thinking\": ..., \"tool\": ..., \"input\": {...}}")
    return "\n\n".join(parts)


def run(mode, max_steps):
    """The loop. Returns finish input, or None if stopped early."""
    history, bad = [], 0
    log = (config.OUT / "history.jsonl").open("a")
    for step in range(1, max_steps + 1):
        print(f"[{mode} {step}] asking Gemini...", end=" ", flush=True)
        t = time.time()
        try:
            raw = llm.ask(build_prompt(mode, history))
        except Exception as e:
            print(f"\nStopped: Gemini not reachable ({str(e)[:120]}). Try again in a few minutes.")
            return None
        print(f"{time.time() - t:.0f}s")
        try:
            wish = json.loads(raw)
            assert isinstance(wish, dict) and "tool" in wish
            reason = safety.check(wish, mode, history)
            gate = "ok" if reason is None else f"REFUSED: {reason}"
        except (ValueError, AssertionError):
            wish, gate = {"raw": raw[:500]}, 'INVALID: reply must be JSON {"thinking", "tool", "input"}'

        result = tools.run(wish["tool"], wish.get("input") or {}) if gate == "ok" else None
        entry = {"step": step, "mode": mode, "wish": wish, "gate": gate, "result": result}
        history.append(entry)
        log.write(json.dumps(entry) + "\n")
        log.flush()
        print(f"[{mode} {step}] {wish.get('tool', '?')} {json.dumps(wish.get('input', ''))[:90]}  ->  {gate if gate != 'ok' else str(result)[:90]}")

        bad = 0 if gate == "ok" else bad + 1
        if bad >= config.MAX_BAD_IN_A_ROW:
            print("Stopped: AI stuck (3 refused/invalid turns in a row)")
            return None
        if gate == "ok" and wish["tool"] == "finish":
            return wish.get("input") or {}
    print(f"Stopped: hit {max_steps} step limit")
    return None


def write_report(summary):
    final = tools.run_pytest()  # verdict comes from Python running pytest, never from the AI
    summary = summary or {"summary": "Agent stopped before finish."}
    lines = [
        "# Report", "",
        f"**pytest (run by Python): {final['passed']} passed, {final['failed']} failed, {final['errors']} errors (exit {final['exit']})**", "",
        "## Summary", str(summary.get("summary", "")), "",
        "## API bugs (found by agent, verified with a second request)",
    ]
    lines += [f"- {b.get('test', '')}: {b.get('what', '')}  (evidence: {b.get('evidence', '')})" if isinstance(b, dict) else f"- {b}"
              for b in summary.get("bugs", [])] or ["- none"]
    lines += ["", "## Tests the agent fixed (its own mistakes)"]
    lines += [f"- {t}" for t in summary.get("fixed_tests", [])] or ["- none"]
    lines += ["", "## Plan status", read("out/plan.md"), "## Last pytest output", "```", final["output"], "```"]
    (config.OUT / "report.md").write_text("\n".join(lines))
    print(f"\nReport: {config.OUT / 'report.md'}  |  pytest: {final['passed']} passed, {final['failed']} failed")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if "prod" in config.BASE_URL:
        sys.exit("BASE_URL looks like production. Refusing to run.")
    config.OUT.mkdir(exist_ok=True)

    if mode == "plan":
        (config.OUT / "history.jsonl").write_text("")  # fresh run
        run("plan", config.PLAN_MAX_STEPS)
        plan = config.OUT / "plan.md"
        if not plan.exists():
            sys.exit("No plan written. Check out/history.jsonl")
        print(f"\nPlan saved: {plan} ({plan.read_text().count('- [ ]')} tests)")
        if input("Review it, then press Enter to execute, or q to quit: ").strip().lower() == "q":
            return
        mode = "execute"

    if mode == "execute":
        if not (config.OUT / "plan.md").exists():
            sys.exit("No out/plan.md. Run: python agent.py plan")
        write_report(run("execute", config.MAX_STEPS))
    else:
        sys.exit("usage: python agent.py [plan|execute]")


if __name__ == "__main__":
    main()
