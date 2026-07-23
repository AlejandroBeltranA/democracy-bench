"""GPT-5.4 non-study capability probe. Synthetic prompt only — no paper probe, no contrast.
Resolves Fable findings 1-3: decode-envelope filtering, reasoning-disable acceptance, and
whether a viable output budget yields a parseable single digit, plus true per-call cost.
Persists every raw response under out/q2_stage2_canary/gpt54_probe/ for audit."""
import json, os, sys, urllib.request, urllib.error
sys.path.insert(0, "src")
from alignment.instrument import measure as M
M._load_local_env()

KEY = os.environ["OPENROUTER_API_KEY"]
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4"
SYS = "You are a wire-format check. Reply with a single digit."
USER = ("This is a non-study connectivity canary; it contains no survey probe and no "
        "rights-floor content. Reply with the digit 1.")
OUT = "out/q2_stage2_canary/gpt54_probe"
os.makedirs(OUT, exist_ok=True)

def headers():
    return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
            "X-OpenRouter-Metadata": "enabled"}

def call(name, body):
    body = dict(body, model=MODEL, messages=[{"role": "system", "content": SYS},
                                             {"role": "user", "content": USER}],
               usage={"include": True})
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers())
    try:
        with urllib.request.urlopen(req, timeout=90, context=M._SSL_CTX) as r:
            d = json.load(r)
        json.dump(d, open(f"{OUT}/{name}.json", "w"), indent=1)
        ch = (d.get("choices") or [{}])[0]
        msg = (ch.get("message") or {})
        u = d.get("usage") or {}
        print(f"[{name}] OK provider={d.get('provider')} finish={ch.get('finish_reason')}")
        print(f"    content={msg.get('content')!r} reasoning_len={len(msg.get('reasoning') or '')}")
        print(f"    usage: prompt={u.get('prompt_tokens')} completion={u.get('completion_tokens')} "
              f"reasoning={ (u.get('completion_tokens_details') or {}).get('reasoning_tokens') } "
              f"cost=${u.get('cost')}")
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", "replace")[:400]
        json.dump({"error": e.code, "body": body_txt}, open(f"{OUT}/{name}.json", "w"), indent=1)
        print(f"[{name}] HTTP {e.code}: {body_txt[:220]}")

# A: our FROZEN envelope — expected to be filtered out (finding 1)
call("A_frozen_envelope", {"temperature": 1.0, "top_p": 1.0, "max_tokens": 4,
     "provider": {"only": ["openai"], "allow_fallbacks": False, "require_parameters": True}})
# B: reasoning-viable, effort none, max_tokens 4 (finding 2+3)
call("B_effortNone_mt4", {"max_tokens": 4, "reasoning": {"effort": "none"},
     "provider": {"only": ["openai"], "allow_fallbacks": False}})
# C: effort none, raised budget
call("C_effortNone_mt16", {"max_tokens": 16, "reasoning": {"effort": "none"},
     "provider": {"only": ["openai"], "allow_fallbacks": False}})
# D: no reasoning param at all, raised budget — what default reasoning costs
call("D_default_mt64", {"max_tokens": 64,
     "provider": {"only": ["openai"], "allow_fallbacks": False}})
print("\nDONE. Raw responses in", OUT)
