# API test agent

    cd test
    pip install -r requirements.txt
    cp .env.example .env        # add GEMINI_API_KEY, BASE_URL
    python agent.py plan        # writes out/plan.md, then Enter = execute, q = quit
    python agent.py execute     # run plan again later without re-planning

You write: api.md, rules.md, .env
Agent writes: out/plan.md, out/history.jsonl, out/test_api.py, out/report.md
Rerun tests later without AI: pytest out
Safety self-check: python safety.py
