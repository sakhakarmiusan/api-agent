import time

import config

_client = None


def ask(prompt):
    """Send prompt to Gemini, return raw text (should be JSON)."""
    global _client
    from google import genai
    from google.genai import types

    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    for attempt in range(5):
        try:
            r = _client.models.generate_content(
                model=config.MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
            )
            return r.text
        except Exception as e:
            code = getattr(e, "code", None)
            if attempt == 4 or (code and 400 <= code < 500 and code != 429):
                raise  # wrong model / bad key: retrying won't help
            print(f"  gemini error, retry in 30s: {e}")
            time.sleep(30)
