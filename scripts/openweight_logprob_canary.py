#!/usr/bin/env python3
"""Open-weight logprob capability canary for Q2 Stage-2.

An OUTCOME-BLINDED synthetic probe. It sends NO study probe content and NO
contrast; it only asks a throwaway multiple-choice question so we can inspect the
logprob distribution AT THE ANSWER POSITION. Its single job: decide whether a
provider-pinned open-weight endpoint returns clean top-k logprobs, so the retired
protective-mass estimator can be revived (or, if not, we keep the v6 sampling path).

Why this exists: endpoint metadata that ADVERTISES `top_logprobs` is necessary but
not sufficient. grok advertised support but capped k at 8; Llama via akashml/fp8
returned logprobs for the WRONG token. Only an empirical probe settles it.

Hardened per Sol's S-F6 and R-E1/R-E5:
  * does nothing on import (guarded by __main__);
  * refuses to spend without --i-understand-this-costs-money;
  * writes one IMMUTABLE raw envelope per call (redacted request, full response,
    response headers, status, generation id, usage, cost, timestamp) and REFUSES
    to overwrite an existing artifact unless --force;
  * pins the provider (only=[tag], allow_fallbacks=false, require_parameters=true);
  * never persists the API key.

Run:
    export OPENROUTER_API_KEY=...
    python scripts/openweight_logprob_canary.py --i-understand-this-costs-money
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

API_URL = "https://openrouter.ai/api/v1/chat/completions"
OUT_DIR = Path("out/q2_stage2_canary/openweight_logprob_reprobe")

TOP_LOGPROBS = 5        # diagnostic: Alibaba caps k at 5; 5 >= the 4-option set
MAX_TOKENS = 32         # raised from 8 so a preamble/reasoning can't truncate the answer
TEMPERATURE = 1.0
TOP_P = 1.0
# Disable reasoning so a thinking model doesn't spend the budget before the answer.
# Ignored (with require_parameters:false) by endpoints that don't support it.
REASONING = {"enabled": False}
# require_parameters:false for the diagnostic so an unsupported param is IGNORED
# (and we can inspect whether logprobs actually return) rather than filtering the
# pinned endpoint to a 404. The real study re-tightens this once the envelope is known.
REQUIRE_PARAMETERS = False

# Provider-pinned targets. tag == the OpenRouter endpoint tag (provider.only).
# `extra` lets a reasoning model receive a reasoning-disable setting; empty by default
# so the canary REVEALS whether reasoning silently consumes the token budget.
TARGETS = [
    {"model": "qwen/qwen3.5-397b-a17b",       "tag": "digitalocean", "extra": {}},
    {"model": "deepseek/deepseek-v4-pro",     "tag": "fireworks",    "extra": {}},
    {"model": "deepseek/deepseek-v4-pro",     "tag": "wandb",        "extra": {}},
    {"model": "meta-llama/llama-4-maverick",  "tag": "digitalocean", "extra": {}},  # non-reasoning control
]

# A throwaway, OUTCOME-BLINDED item with NO correct answer (landscape preference,
# nothing to do with the study). Genuine uncertainty is deliberate: it gives the
# position-0 distribution a reason to SPREAD across the option digits, so we can
# see whether the endpoint's top-k actually covers the option set (what the
# protective-mass estimator needs) rather than saturating on one determinate token.
SYSTEM = ("Answer with exactly one character: the digit (1, 2, 3, or 4) of your chosen "
          "option. Output nothing else — no words, no punctuation, no explanation.")
USER = ("Which of these do you personally prefer?\n"
        "Option 1: mountains\nOption 2: beaches\nOption 3: forests\nOption 4: deserts\n"
        "Reply with only the option number.")
OPTION_TOKENS = {"1", "2", "3", "4"}


def build_body(model: str, tag: str, extra: dict) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "logprobs": True,
        "top_logprobs": TOP_LOGPROBS,
        "reasoning": REASONING,
        "provider": {"only": [tag], "allow_fallbacks": False,
                     "require_parameters": REQUIRE_PARAMETERS},
        "usage": {"include": True},
        **extra,
    }


def redacted_headers(key: str) -> dict:
    # headers actually sent; the persisted copy redacts the credential
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-OpenRouter-Metadata": "enabled",
    }


def call(body: dict, key: str, timeout: int = 60):
    data = json.dumps(body).encode()
    req = urllib.request.Request(API_URL, data=data, method="POST")
    for h, v in redacted_headers(key).items():
        req.add_header(h, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def analyze(resp_json: dict) -> dict:
    """Inspect position-0 top_logprobs for what the protective-mass estimator needs:
    do the option digits appear in the top-k, and do they carry non-trivial mass?
    Fail-closed on any missing structure."""
    import math
    out = {"logprobs_present": False, "k_returned": 0, "option_tokens_seen": [],
           "option_coverage": 0, "option_mass": None, "argmax_token": None,
           "argmax_prob": None, "saturated": None, "usable_for_estimator": False,
           "content": None, "finish_reason": None, "error": None}
    try:
        choice = resp_json["choices"][0]
        out["finish_reason"] = choice.get("finish_reason")
        out["content"] = (choice.get("message") or {}).get("content")
        lp = choice.get("logprobs")
        if not lp or not lp.get("content"):
            out["error"] = "no logprobs returned (endpoint advertised support but sent none)"
            return out
        top = lp["content"][0]["top_logprobs"]
        out["logprobs_present"] = True
        out["k_returned"] = len(top)
        toks = [(t["token"].strip(), t.get("logprob")) for t in top]
        seen = sorted({t for t, _ in toks} & OPTION_TOKENS)
        out["option_tokens_seen"] = seen
        out["option_coverage"] = len(seen)
        # summed probability mass sitting on the option digits within the returned top-k
        opt_mass = sum(math.exp(lp_) for t, lp_ in toks
                       if t in OPTION_TOKENS and lp_ is not None)
        out["option_mass"] = round(opt_mass, 6)
        best_tok, best_lp = max(toks, key=lambda kv: (kv[1] if kv[1] is not None else -1e9))
        out["argmax_token"] = best_tok
        out["argmax_prob"] = round(math.exp(best_lp), 6) if best_lp is not None else None
        out["saturated"] = (out["argmax_prob"] is not None and out["argmax_prob"] > 0.999)
        # usable if >=2 option digits carry visible mass and it isn't fully saturated
        out["usable_for_estimator"] = (out["option_coverage"] >= 2 and not out["saturated"])
    except (KeyError, IndexError, TypeError) as e:
        out["error"] = f"structure missing: {e!r}"
    return out


def cost_of(resp_json: dict):
    u = resp_json.get("usage") or {}
    for k in ("cost", "total_cost"):
        if isinstance(u.get(k), (int, float)):
            return float(u[k])
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-understand-this-costs-money", action="store_true",
                    dest="ack", help="required acknowledgement that this makes PAID calls")
    ap.add_argument("--force", action="store_true", help="overwrite existing artifacts")
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not set — export it first.", file=sys.stderr)
        return 2
    if not args.ack:
        print(f"This will make {len(TARGETS)} PAID OpenRouter calls. "
              f"Re-run with --i-understand-this-costs-money to proceed.", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_cost, summary = 0.0, []
    for t in TARGETS:
        safe = f"{t['model'].replace('/', '__')}__{t['tag']}"
        path = OUT_DIR / f"{safe}.json"
        if path.exists() and not args.force:
            print(f"SKIP (exists, use --force): {path}", file=sys.stderr)
            continue
        body = build_body(t["model"], t["tag"], t["extra"])
        status, headers, raw = call(body, key)
        try:
            resp_json = json.loads(raw)
        except json.JSONDecodeError:
            resp_json = {"_unparseable_body": raw}
        c = cost_of(resp_json)
        total_cost += c or 0.0
        envelope = {
            "target": t,
            "ts": time.time(),
            "http_status": status,
            "request": {**body, "_note": "credential not stored; sent via Authorization header"},
            "response_headers": headers,
            "response": resp_json,
            "generation_id": resp_json.get("id"),
            "usage": resp_json.get("usage"),
            "returned_cost": c,
            "analysis": analyze(resp_json) if status == 200 else None,
        }
        path.write_text(json.dumps(envelope, indent=2))
        a = envelope["analysis"] or {}
        summary.append((t["model"], t["tag"], status, c, a))
        print(f"\n### {t['model']} @ {t['tag']}  [HTTP {status}]  cost={c}")
        if status == 200:
            print(f"  content={a.get('content')!r} finish={a.get('finish_reason')}")
            print(f"  logprobs_present={a.get('logprobs_present')} k_returned={a.get('k_returned')} "
                  f"option_coverage={a.get('option_coverage')}/4 seen={a.get('option_tokens_seen')}")
            print(f"  argmax={a.get('argmax_token')!r} p={a.get('argmax_prob')} "
                  f"option_mass={a.get('option_mass')} saturated={a.get('saturated')} "
                  f"USABLE={a.get('usable_for_estimator')}")
            if a.get("error"):
                print(f"  ERROR: {a['error']}")
        else:
            print(f"  body: {raw[:300]}")

    print(f"\n=== canary total returned cost: ${total_cost:.6f} over "
          f"{len(summary)} calls; artifacts in {OUT_DIR} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
