"""Real actions. Only Python runs these; the AI can only ask."""
import json
import re
import subprocess
import sys

import httpx

import config

LIMIT = 2000  # chars kept from big outputs so history stays small


def _cut(text):
    text = text if isinstance(text, str) else json.dumps(text)
    return text if len(text) <= LIMIT else text[:LIMIT] + "...[cut]"


def send_request(method, path, body=None, headers=None):
    h = {"Authorization": f"Bearer {config.TOKEN}"} if config.TOKEN else {}
    for k, v in (headers or {}).items():
        if v in ("", None):
            h.pop(k, None)  # lets AI test "no token"
        else:
            h[k] = v
    r = httpx.request(method.upper(), config.BASE_URL + path, json=body, headers=h, timeout=30)
    try:
        out = r.json()
        if len(json.dumps(out)) > LIMIT:
            out = _cut(out)
    except ValueError:
        out = _cut(r.text)
    return {"status": r.status_code, "body": out}


def write_plan(content):
    (config.OUT / "plan.md").write_text(content)
    return f"plan saved, {content.count('- [ ]')} tests"


def update_plan(id, mark, note=""):
    if mark not in ("x", "!"):
        return "ERROR: mark must be 'x' or '!'"
    p = config.OUT / "plan.md"
    lines = p.read_text().splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"- \[.\]\s+{re.escape(id)}\b", line):
            lines[i] = f"- [{mark}]" + line[5:].split("  | ")[0] + (f"  | {note}" if note else "")
            p.write_text("\n".join(lines) + "\n")
            return f"{id} marked {mark}"
    return f"ERROR: {id} not found in plan"


def write_file(path, content):
    f = config.HERE / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    return f"written {path}, {content.count(chr(10)) + 1} lines"


def read_file(path):
    f = config.HERE / path
    return _cut(f.read_text()) if f.exists() else f"ERROR: {path} not found"


def run_pytest():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "out", "-q", "--tb=short", "-p", "no:cacheprovider"],
        cwd=config.HERE, capture_output=True, text=True, timeout=300,
    )
    out = r.stdout + r.stderr
    count = lambda word: int(m.group(1)) if (m := re.search(rf"(\d+) {word}", out)) else 0
    return {"exit": r.returncode, "passed": count("passed"), "failed": count("failed"),
            "errors": count("error"), "output": out[-3000:]}


def finish(**kwargs):
    return "done"


FUNCS = {f.__name__: f for f in (send_request, write_plan, update_plan, write_file, read_file, run_pytest, finish)}


def run(tool, inp):
    try:
        return FUNCS[tool](**inp)
    except Exception as e:  # bad args, network down, etc. AI sees the error and adapts
        return f"ERROR: {type(e).__name__}: {e}"
