import os
from pathlib import Path

HERE = Path(__file__).parent

# load .env (KEY=VALUE lines) without extra dependency
env = HERE / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

BASE_URL = os.getenv("BASE_URL", "http://localhost:3000").rstrip("/")
TOKEN = os.getenv("TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("MODEL", "gemini-3.8-flash")

PLAN_MAX_STEPS = 8        # plan mode turns
PLAN_MAX_REQUESTS = 3     # real requests allowed while planning
MAX_STEPS = 100           # execute mode turns (about 3 per test + writing/running pytest)
MAX_BAD_IN_A_ROW = 3      # refused/invalid turns in a row = stuck, stop
ALLOW_DELETE = False
OUT = HERE / "out"
