# AI API Testing Agent — Project Brief & Handoff

**Owner:** USAN (QA Engineer, Niural)
**Build folder:** `/Users/usansakhakarmi/usan/apiagent` (currently empty)
**Status:** Design agreed. No code written yet.
**Purpose of this document:** Give a fresh Claude/Cowork session everything it needs to start building, with no prior conversation.

---

## 1. What we are building

A tool that generates and runs API tests automatically.

**Today:** I write every API test by hand.
**Goal:** I provide the API spec, the business rules, and a few edge cases. The system produces runnable Pytest code, executes it against our API, decides PASS/FAIL, and explains any failures.

**Scope — API testing only.** Explicitly NOT in v1:
- No database testing (no DynamoDB, no PostgreSQL)
- No UI testing, no browser automation
- No performance/load testing

---

## 2. Background — the source document

A colleague produced `AI_Agent_API_Testing_Framework_Architecture.pdf`, which describes an 8-agent architecture (Orchestrator, API Analysis, Test Generator, Test Data, Execution, Validation, AI Analysis, Reporting) plus a folder layout.

**Important: that PDF is a design on paper. It contains no code and no working implementation.** Treat it as a blueprint to validate, not a system to inherit.

What we kept from it:
- The core principle (section 12): AI for reasoning, deterministic Python for execution.
- The broad agent responsibilities.

What we changed:
- **Removed all database testing** — the PDF's Execution Agent hits "REST API + DATABASE", Validation checks "database state", and the folder tree has a `database/` package. All cut.
- **Made code generation explicit.** The PDF says "Test Generator converts requirements into test scenarios" but never says whether the output is a list of ideas or runnable code. Producing executable Pytest is the thing we are actually building.
- **Added a feedback loop.** The PDF's flow is one-way. Real use needs: generate → run → some tests are wrong → fix → regenerate.
- **Flattened the folder structure.** One folder per agent is overhead for ~150-line modules.

---

## 3. The non-negotiable design principle

```
AI decides WHAT to test.
Python decides WHETHER it passed.
```

The AI writes `assert response.status_code == 201`. Python runs that assert. The model never looks at a response and declares a verdict.

Break this and the suite becomes non-deterministic — same API, same run, different results. Every other decision below is downstream of protecting this rule.

| Use AI for | Use deterministic Python for |
|---|---|
| Understanding requirements | Sending HTTP requests |
| API spec analysis | Authentication |
| Test scenario generation | Assertions |
| Writing test code | Status code / response validation |
| Failure analysis & root cause | Test execution |
| | PASS/FAIL determination |
| | Logging and reporting |

---

## 4. Confirmed environment decisions

| Item | Decision | Notes |
|---|---|---|
| API environment | AWS, managed in **Postman** | Postman collection is the primary input, not hand-written YAML |
| Test runner | **Python + Pytest** | |
| HTTP client | **httpx** (or requests) | |
| LLM | **Google Gemini, free tier** | ~15 requests/min, daily cap. Use `google-genai` SDK (not the older `google-generativeai`) |
| Orchestration framework | **None** — no LangChain, CrewAI, AutoGen | It is six sequential function calls; a framework makes debugging harder and can be added later |
| Validation | **Pydantic** models for every LLM output | Structured JSON via Gemini `response_schema` |
| Reporting | `pytest-json-report` + `jinja2` HTML | Skip Allure for now (needs a Java runtime) |

### Open items to resolve at build time
- **Network reachability.** Is the AWS QA environment publicly reachable, or behind a VPC/VPN/IP allowlist? If private, Pytest must run on the local machine, not in a cloud session. Find out by trying one request — do not guess.
- **Auth mechanism.** API Gateway usually means Cognito token, IAM signature, or static API key. Each is a different `conftest.py`. If Postman handles it with a pre-request script today, that script is the spec.
- **Saved error examples in Postman.** If the collection has a saved 422/400 validation response, the generator learns the real error shape instead of guessing. High-leverage; check and add a few if missing.

### Known risk — free Gemini tier
Free-tier keys generally mean **Google may use the data for training**. API specs and request/response payloads would be sent. Acceptable for a prototype on test data; must be revisited before this touches anything with real customer data.

---

## 5. Architecture — the pipeline (v1)

Six stages. Each reads one file and writes another. **Agents do not call each other.** The orchestrator calls each stage in order.

```
INPUT:  Postman collection  +  requirements.yaml (hand-written)
            ↓
[AI]   Stage 1  ANALYZE      → artifacts/analysis.json
            ↓
[AI]   Stage 2  SCENARIOS    → artifacts/scenarios.json      ← HUMAN REVIEW POINT
            ↓
[AI]   Stage 3  CODE GEN     → tests/generated/test_xxx.py
            ↓
       Syntax check (ast.parse) — regenerate once if broken
            ↓
[CODE] Stage 4  EXECUTE      → pytest + httpx → real AWS API
            ↓
       ASSERTIONS DECIDE PASS/FAIL  (no AI anywhere near this)
            ↓
       artifacts/pytest_report.json
            ↓
       PASS ─────────────────────┐
       FAIL → [AI] Stage 5 DIAGNOSE → artifacts/failure_analysis.json
            ↓                       ↓
       Stage 6  REPORT  → reports/report.html
```

### Why files between stages, not function calls
1. **Debuggable** — open the file and look; no tracing through agent conversations.
2. **Cheap iteration** — tuning the code-gen prompt reuses the same `scenarios.json` for free. Essential on a rate-limited free tier.
3. **Human checkpoint** at the cheapest place to fix a mistake (scenarios, before code exists).
4. **Replaceable** — swap Gemini for another model, or hand-write `scenarios.json`, and nothing else notices.

Build a `--from-stage` flag early so later stages can rerun without re-burning LLM calls.

### Cost per endpoint
3 LLM calls to generate + 1 per failing test. An endpoint with 15 tests and 3 failures ≈ 6 calls. Comfortably inside the free tier. This is a consequence of the architecture — per-test LLM calls or chatty inter-agent messaging would be 50+ calls and rate-limit on the first endpoint.

---

## 6. What the data looks like at each hop

**Input (hand-written, the only per-API work):**
```yaml
endpoint: create_employee     # matches the Postman request name
requirements:
  - Email must be unique
  - Salary must be greater than 0
edge_cases:
  - Duplicate email
  - Salary = 0
  - Missing auth token
```

**Stage 1 → analysis.json**
```json
{
  "method": "POST", "path": "/employees",
  "auth": { "type": "bearer", "required": true },
  "fields": [
    { "name": "email", "type": "string", "required": true,
      "format": "email", "unique": true },
    { "name": "salary", "type": "number", "required": true,
      "min": 1, "boundaries": [0, 1, 2, 999999999] }
  ],
  "responses": { "success": 201, "validation_error": 422, "unauthorized": 401 }
}
```
`boundaries` was derived, not supplied. `validation_error: 422` should come from a **saved Postman example**, not a guess — this is the single highest-value fact in the file.

**Stage 2 → scenarios.json** (reviewable, diffable, hand-editable)
```json
[
  { "id": "TC001", "category": "positive", "desc": "Valid employee created",
    "payload": {"name":"John","email":"<unique>","salary":50000},
    "expect_status": 201, "expect": ["body.id exists"] },
  { "id": "TC007", "category": "boundary", "desc": "Salary = 0 rejected",
    "payload": {"name":"John","email":"<unique>","salary":0},
    "expect_status": 422 }
]
```

**Stage 3 → test file**
```python
def test_TC007_salary_zero_rejected(api_client, unique_email):
    payload = {"name": "John", "email": unique_email, "salary": 0}
    response = api_client.post("/employees", json=payload)
    assert response.status_code == 422, f"Got {response.status_code}: {response.text}"
```

**Stage 5 → failure_analysis.json**
```json
{ "test": "TC007",
  "classification": "TEST_BUG",
  "root_cause": "API returns 400 for salary=0, not 422.",
  "suggested_action": "Correct expect_status for boundary cases to 400." }
```

The `classification` field — **API_BUG / TEST_BUG / DATA_ISSUE / ENV_ISSUE** — is the most useful output in the system. On a freshly generated suite most failures are TEST_BUG (the generator assumed wrong), and knowing which kind turns a wall of red into a short fix list.

---

## 7. Agents vs. pipeline — an honest distinction

The v1 above is a **prompt chain / AI workflow**, not a true agent. The AI does the reasoning *inside* each step; the control flow is hardcoded in `orchestrator.py`.

```
LEVEL 0  Fixed code            conftest.py, runner, report
LEVEL 1  Prompt chain          ← v1 is here
LEVEL 2  Agent with tools      LLM calls a tool, sees the result, decides the next move
LEVEL 3  Autonomous agent      sets its own goals
```

This is deliberate: a chain is debuggable, cheap (3 calls vs 10–30), and sufficient for one-shot reasoning tasks.

### The upgrade target (v2): Stage 5 becomes a real agent

Failure diagnosis is the one step that genuinely needs to act, observe, and decide again:

```
observe   TC007 failed — expected 422, got 400
think     my assumption, or an API bug?
act       send salary = -5 and salary = 0, compare
observe   both return 400 with {"error": "validation_failed"}
think     consistent → my expectation was wrong
act       grep other scenarios for the same assumption
observe   TC008, TC009 share it
conclude  TEST_BUG — 3 scenarios need expect_status 400
```

Plus the self-correcting loop the source PDF is missing entirely:
```
generate → run → fail → diagnose → fix scenarios → regenerate → run again
    ▲                                                            │
    └────────────────────────────────────────────────────────────┘
```

### How an agent actually works (mechanically)

An LLM can only turn text into text. It cannot send a request or open a file. "The AI used a tool" really means:

```
1. AI writes TEXT: "I want to send this request"
2. Python reads that text
3. Python checks whether it is allowed      ← safety gate
4. Python actually sends the request
5. Python appends the result to the history as TEXT
6. Loop: history is re-sent, AI picks the next move
```

The loop itself, in full:

```python
def run_agent(goal, facts):
    history = []
    for step in range(1, 21):                 # guardrail: max 20 steps
        letter = build_prompt(goal, TOOLS, facts, history)
        wish   = ask_gemini(letter)           # {"thinking","tool","input"}

        ok, reason = is_safe(wish)            # Python, hardcoded rules
        if not ok:
            history.append({"step": step, "wish": wish,
                            "result": f"REFUSED: {reason}"})
            continue

        if wish["tool"] == "finish":
            return wish["input"]["summary"]

        result = TOOLS[wish["tool"]](**wish["input"])
        history.append({"step": step, "wish": wish, "result": result})

    return "Stopped: hit the 20 step limit."
```

Goal, tools and facts never change between turns. **Only the history grows** — that is the entire memory mechanism.

### Two things to build correctly in v1 so v2 is an upgrade, not a rewrite
1. **Every stage reads and writes files** — an agent can then rewrite `scenarios.json` and re-trigger codegen. That is the feedback edge, pre-wired.
2. **`send_request()` is a standalone function, not buried inside Pytest** — so the diagnose agent can call it as a tool to probe the API.

### Agent tool list (v2)
`read_postman()`, `send_request(method, path, body, headers)`, `write_file()`, `read_file()`, `run_pytest()`, `read_results()`, `finish(summary)`

---

## 8. The two different "checks" — do not confuse them

| | Safety check | Pass/fail check |
|---|---|---|
| When | Before each agent action | After the request, in the test |
| Where | `core/safety.py` | inside the generated test file |
| Asks | "Is the AI allowed to do this?" | "Is the API correct?" |
| Written by | **Human** | **AI** |
| Run by | Python | Python |
| Can AI decide? | Never | Never |

```python
# core/safety.py  — human-written, AI never touches it
ALLOWED_TOOLS   = ["send_request", "write_file", "run_pytest", "finish"]
BLOCKED_METHODS = ["DELETE"]

def is_safe(wish):
    if wish["tool"] not in ALLOWED_TOOLS:
        return False, "That tool does not exist."
    if wish["tool"] == "send_request":
        if wish["input"]["method"] in BLOCKED_METHODS:
            return False, "DELETE is not allowed."
        if "prod" in os.getenv("BASE_URL"):
            return False, "Production is not allowed."
    return True, "ok"
```

---

## 9. Chained APIs (the W-2 hiring flow)

The real target is not one endpoint — it is a chain:

```
1  POST /employees                    name, email, phone, DOB  → returns employee_id
2  POST /employees/{id}/address       street, city, state, country, zip
3  POST /employees/{id}/employment    position, start date, salary, type = W-2
4  POST /employees/{id}/tax-info      SSN, W-4 filing status, state tax
5  POST /employees/{id}/onboard       → status becomes ACTIVE
```

Chains add three problems single endpoints do not have:
1. **Data must flow** — step 1's `employee_id` is needed by steps 2–5.
2. **Order matters** — if step 2 fails, steps 3–5 cannot run (mark SKIPPED, not FAILED).
3. **Half-finished records** — step 1 succeeds, step 3 fails. Is that state allowed? This is where the serious bugs live.

### How the ID travels — different in each phase

**During agent exploration:** no code handles it. The AI reads `"employee_id": "emp_8821"` in the history text and types it into its next wish.

**In the generated test file:** a Pytest fixture.
```python
@pytest.fixture
def new_employee():
    result = send_request("POST", "/employees", {
        "name": "Test User",
        "email": f"test_{uuid4().hex[:8]}@test.com",   # unique per run
        "phone": "5551234", "dob": "1990-05-10"
    })
    assert result["status"] == 201
    return result["body"]["employee_id"]
```

### The chain test that matters most
```python
def test_cannot_onboard_without_tax_info(api, new_employee):
    emp_id = new_employee
    api.post(f"/employees/{emp_id}/address",    json=VALID_ADDRESS)
    api.post(f"/employees/{emp_id}/employment", json=VALID_JOB)
    # tax-info deliberately skipped
    response = api.post(f"/employees/{emp_id}/onboard")
    assert response.status_code == 400, "Employee became ACTIVE without tax info"
```
Most suites test each endpoint alone and never ask "what if I skip step 4?" For a W-2 employee, becoming ACTIVE with no SSN/W-4 on file is a payroll and compliance risk, not just a software bug.

### Chain-specific requirements
| Need | Why |
|---|---|
| Unique data per run (email, SSN) | Otherwise run 2 fails for the wrong reason |
| Cleanup of created records | Every run creates employees; the QA DB fills up |
| ID passing via fixtures | Step 1's output feeds steps 2–5 |
| Skip rule | Step 1 fails → mark 2–5 SKIPPED, not FAILED |
| Higher step limit, same cap | A 5-step chain can use ~16 AI calls ≈ 2 minutes on free-tier rate limits |

---

## 10. Who writes what

| Artifact | Written by | How often |
|---|---|---|
| `core/http.py` — one generic `send_request()` | Human | Once |
| `core/safety.py` — safety rules | Human | Once |
| `agent.py` / `orchestrator.py` | Human | Once |
| `prompts/*.txt` | Human | Once, then tuned |
| `conftest.py` — auth, base URL, fixtures | Human | Once |
| `config/qa.yaml`, `.env` | Human | Once per environment |
| `rules/<endpoint>.yaml` — business rules + edge cases | **Human** | Per API (~15 min) |
| `tests/generated/test_*.py` | AI | Every run |
| Generic edge cases (empty, null, wrong id, no auth, oversized) | AI | Every run |
| The `assert` lines | AI | Every run |
| Failure explanations | AI | Every run |

The one generic HTTP function covers every endpoint:
```python
def send_request(method, path, body=None, headers=None):
    url = os.getenv("BASE_URL") + path
    final_headers = {"Authorization": f"Bearer {os.getenv('TOKEN')}"}
    if headers:
        final_headers.update(headers)        # lets AI override for auth tests
    r = httpx.request(method, url, json=body, headers=final_headers, timeout=30)
    return {"status": r.status_code, "body": r.json(), "headers": dict(r.headers)}
```

**Edge case division:** the AI reliably generates generic patterns (empty string, missing field, wrong/empty ID, IDOR with another tenant's ID, no auth header, expired token, SSN with letters, 500-char name, extra unknown field, salary as string, past/far-future dates). It will **never** invent domain rules like "a W-2 employee in California must have SDI configured." Those must be written by hand.

---

## 11. Recommended project structure

```
apiagent/
├── orchestrator.py           # the pipeline (v1)
├── agent.py                  # the loop (v2)
├── agents/
│   ├── analyzer.py
│   ├── generator.py
│   ├── data_agent.py
│   └── failure_analyzer.py
├── core/
│   ├── http.py               # send_request() — standalone, reusable as a tool
│   ├── llm.py                # Gemini wrapper, retries, JSON parsing
│   ├── safety.py             # guardrails
│   ├── models.py             # Pydantic schemas for every artifact
│   └── config.py
├── prompts/
│   ├── analysis.txt
│   ├── scenario_generation.txt
│   ├── code_generation.txt
│   └── failure_analysis.txt
├── rules/
│   └── hire_w2_employee.yaml
├── tests/
│   ├── conftest.py           # HAND-WRITTEN: base_url, auth, client, fixtures
│   └── generated/            # AI writes here; gitignore initially
├── artifacts/                # intermediate JSON between stages
├── reports/
├── config/qa.yaml
├── .env                      # BASE_URL, TOKEN, GEMINI_KEY — never committed
└── requirements.txt
```

`conftest.py` is hand-written on purpose: auth, base URL and the session client are stable infrastructure and must not be regenerated on every run. Generated tests only consume the fixtures.

---

## 12. Build order — strict, do not skip

**Slice 1 — one endpoint, NO AI.** Hand-write `conftest.py` and one Pytest file against a real endpoint. Get it green.

Two reasons this is not a wasted step:
1. It proves auth, URLs and execution work — every later failure is then an AI problem, not a plumbing problem.
2. **That hand-written file becomes the few-shot example in the code-gen prompt.** It is the most reused artifact in the project. Few-shot examples beat instructions for code generation, consistently.

**Slice 2 — AI generates scenarios.** YAML in, `scenarios.json` out, Pydantic-validated. Read them. Do they cover the listed edge cases and find new ones? Tune the prompt. No code generation yet.

**Slice 3 — AI generates code.** Scenarios in, `.py` out. It will be wrong at first (hallucinated fixtures, wrong assertion style). The fix is pasting the complete Slice 1 test into the prompt with "match this structure exactly."

**Slice 4 — wire the runner.** Pytest on the generated file, capture JSON. Pure plumbing.

**Slice 5 — failure analysis.** Deliberately break something (wrong URL, or assert 200 where the API returns 201) to get real failures. Check whether the root-cause guesses are useful or just restate the error.

**Slice 6 — the report.** Jinja2 template, one page.

**Slice 7 — second endpoint.** The real test of the framework. Write a new YAML and run end to end *without touching framework code*. If framework code must change, that code belonged in config or the prompt — fix that, and only then is it a framework rather than one clever script.

**Slice 8 (later) — upgrade Stage 5 to a real agent loop.**

Add a `--dry-run` flag from day one (stop after generating). It will be used constantly while tuning prompts and costs nothing.

---

## 13. Day-to-day usage once built

**One-time setup:** ~1–2 days (env, deps, `.env`, `conftest.py`, prompts, one no-AI test).

**Per new API:** ~20–30 minutes
1. Find it in Postman
2. Write `rules/<endpoint>.yaml` — requirements + edge cases (~15 min, the only real work)
3. `python orchestrator.py --spec <file> --dry-run`
4. **Review `artifacts/scenarios.json`** — the cheapest place to catch a wrong assumption
5. Skim `tests/generated/test_*.py`
6. `python orchestrator.py --spec <file> --env qa`
7. Read `reports/report.html`
8. Act: REAL BUG → raise a ticket. TEST BUG → fix the scenario, regenerate (~1 min).

For comparison, writing ~10 tests by hand is 2–3 hours.

**After that:** just `pytest tests/generated/` — before a release, after an API change, nightly, or to confirm a reported bug. Regenerate only when the API itself changes (~5 min).

---

## 14. Hard constraints and warnings

1. **Never point this at production.** The agent chooses its own requests and creates records. On production that is real damage — in a payroll system, fake hired employees.
2. **Review generated tests**, especially for the first ~5 endpoints. The generator will assume 400 where the API returns 422, or invent response fields. A suite nobody has read is false confidence, not a safety net. The review shrinks as prompts improve but should never reach zero.
3. **Gemini free tier ≈ 15 requests/min.** Pipeline ≈ 3 calls/API (fine). Agent loop ≈ 10–25 calls/API (one endpoint can consume a minute). Run endpoints sequentially, not in parallel.
4. **Always cap agent steps** (20) and log every step. Without the cap, one bad run exhausts the daily quota.
5. **Free Gemini keys generally mean data is used for training.** Fine for test data; revisit before real customer data is involved.
6. **Model choice:** Flash is fine for analysis, scenario generation and failure analysis. Code generation is the hardest step for a small model — if generated tests come out messy, try Pro there first before changing anything else.

---

## 15. Immediate next action

Pick **one endpoint** for Slice 1. Best candidate: a POST with validation rules and auth — ideally the first step of the W-2 hiring chain.

Needed for it:
- Method, path, request body with field types
- A success response example
- **An error response example** (this matters more than people expect — if the API returns 422 and the generator assumes 400, every negative test fails for the wrong reason)
- How auth works (Cognito token? IAM signature? static key? what does the Postman pre-request script do?)
- The business rules and edge cases for that endpoint

Fastest path: read the Postman workspace directly (Postman MCP tools were available in the originating session), identify a good candidate endpoint, report what is there and what is missing, then build Slice 1.
