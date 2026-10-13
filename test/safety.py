"""Gate. Human-written. Checks if the AI is ALLOWED to do something, not if the API is correct."""
import config

TOOLS = {
    "plan": {"send_request", "write_plan", "finish"},
    "execute": {"send_request", "update_plan", "write_file", "read_file", "run_pytest", "finish"},
}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _inside_out(path):
    try:
        return (config.HERE / path).resolve().is_relative_to(config.OUT.resolve())
    except Exception:
        return False


def _done(history, tool):
    return sum(1 for h in history if h["gate"] == "ok" and h["wish"].get("tool") == tool)


def check(wish, mode, history):
    """Return None if allowed, else a reason string."""
    tool, inp = wish.get("tool"), wish.get("input") or {}
    if tool not in TOOLS[mode]:
        return f"tool '{tool}' not allowed in {mode} mode. Allowed: {sorted(TOOLS[mode])}"
    if not isinstance(inp, dict):
        return "input must be an object"

    if tool == "send_request":
        method, path = str(inp.get("method", "")).upper(), str(inp.get("path", ""))
        if method not in METHODS:
            return f"method must be one of {sorted(METHODS)}"
        if method == "DELETE" and not config.ALLOW_DELETE:
            return "DELETE not allowed"
        if not path.startswith("/") or "://" in path:
            return "path must start with '/' (base URL is fixed)"
        if mode == "plan" and _done(history, "send_request") >= config.PLAN_MAX_REQUESTS:
            return f"plan mode allows only {config.PLAN_MAX_REQUESTS} requests. Now call write_plan"

    if tool in ("write_file", "read_file"):
        path = str(inp.get("path", ""))
        if not _inside_out(path):
            return "path must be inside out/ (e.g. out/test_api.py)"
        if tool == "write_file" and not path.endswith((".py", ".md")):
            return "only .py or .md files"

    if tool == "finish":
        if mode == "plan" and not _done(history, "write_plan"):
            return "call write_plan first"
        if mode == "execute" and not _done(history, "run_pytest"):
            return "call run_pytest first"
    return None


if __name__ == "__main__":  # self-check: python safety.py
    ok = {"gate": "ok", "wish": {"tool": "send_request"}}
    assert check({"tool": "rm", "input": {}}, "execute", [])
    assert check({"tool": "send_request", "input": {"method": "DELETE", "path": "/orders/1"}}, "execute", [])
    assert check({"tool": "send_request", "input": {"method": "GET", "path": "https://prod.x.com/a"}}, "execute", [])
    assert check({"tool": "send_request", "input": {"method": "POST", "path": "/cart", "body": {"quantity": -5}}}, "execute", []) is None
    assert check({"tool": "send_request", "input": {"method": "GET", "path": "/x"}}, "plan", [ok] * 3)
    assert check({"tool": "write_file", "input": {"path": "../server.js", "content": ""}}, "execute", [])
    assert check({"tool": "write_file", "input": {"path": "out/test_api.py", "content": ""}}, "execute", []) is None
    assert check({"tool": "finish", "input": {}}, "execute", [])
    assert check({"tool": "write_plan", "input": {}}, "execute", [])
    print("safety ok")
