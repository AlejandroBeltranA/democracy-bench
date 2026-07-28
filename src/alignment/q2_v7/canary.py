"""Q2 Stage-2 v7.2 minimal synthetic capability canary.

This is the ONLY paid step the signed v7.2 amendment authorizes (staged authorization
step 2). It sends a SYNTHETIC, non-study prompt — no probe content, no contrast, no
estimand — and verifies exactly five things:

  1. authentication;
  2. wire format (the frozen envelope accepted under `require_parameters:true`);
  3. routing metadata (the frozen C1 provider-audit proof);
  4. usage/cost capture (returned cost, fail-closed);
  5. restart (an already-persisted draw is never repaid).

It additionally records the R-V7-1 reasoning-off evidence (reasoning tokens must be
EXACTLY 0), because that is the binding capability question for these thinking models.

It does NOT run the smoke, the study, or any endpoint promotion: the post-signature
reasoning-off/cost gate is a separate, separately authorized step.

Usage:
    .venv/bin/python -m alignment.q2_v7.canary --i-have-authorized-paid-spend
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from alignment.q2_v7 import envelope as E
from alignment.q2_v7 import identity as I
from alignment.q2_v7 import ledger as L
from alignment.q2_v7.gate import (
    BACKOFF_BASE_S,
    BACKOFF_CAP_S,
    MAX_ATTEMPTS,
    PANEL_ORDER,
    FALLBACK_SEQUENCES,
    REQUEST_WINDOW_S,
)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = ROOT / "out" / "q2_stage2_v7_canary"

#: Prior paid Q2 record directories reconciled from ACTUAL persisted records (R-V7-6).
#: Only the v5-era `raw/` dirs are listed: those records carry a machine-readable returned
#: cost. Sibling files such as `gate_smoke.json` are summary artifacts, not paid records,
#: and the enclosing dirs are therefore deliberately NOT reconciled wholesale.
PRIOR_RECORD_DIRS: tuple[Path, ...] = (
    ROOT / "out" / "q2_stage2_canary" / "raw",
    ROOT / "out" / "q2_stage2_smoke_4omini" / "raw",
    ROOT / "out" / "q2_stage2_smoke_4o" / "raw",
    ROOT / "out" / "q2_stage2_smoke_llama_v2" / "raw",
)

#: The pre-v7 diagnostic canaries were written by ad-hoc probe scripts whose artifacts do
#: not carry a machine-readable returned cost in any recognised field. Rather than force-fit
#: a schema onto them, they are debited at documented conservative UPPER bounds and labelled
#: non-reconciled, exactly as R-V7-6 prescribes; the cumulative total is then not exact.
PRIOR_DIAGNOSTIC_COMPONENTS: tuple[L.NonReconciledComponent, ...] = (
    L.NonReconciledComponent(
        label="gpt54_capability_probe",
        upper_bound_usd=0.0008,
        reason="ad-hoc probe artifacts carry no machine-readable returned cost; the memo's "
               "claimed $0.0008 round total is debited as a conservative upper bound "
               "(persisted successful responses support only $0.0006)"),
    L.NonReconciledComponent(
        label="openweight_logprob_canary_rounds",
        upper_bound_usd=0.0011,
        reason="ad-hoc diagnostic artifacts store cost under `returned_cost`, which is not a "
               "recognised ledger field; the console-logged round totals "
               "($0.000646 + $0.000214 + $0.000140) are debited rounded up"),
    L.FORCE_OVERWRITTEN_CANARY,
)

# --- the synthetic, non-study probe -------------------------------------------------
# Deliberately contentless: no political item, no payload, no guard, no option order.
# It cannot estimate any frozen contrast, so viewing its reply reveals no outcome.
CANARY_SYSTEM = ("Answer with exactly one character: a single digit from 1 to 4. "
                 "Output nothing else — no words, no punctuation, no explanation.")
CANARY_USER = "Reply with the digit 2."
#: The prompt asks for exactly this option, so the canary can assert the ANSWER, not just
#: the wire format (R-C6).
EXPECTED_OPTION = 2

STAGE = "canary"
BUCKET = "canary"


class CanaryError(RuntimeError):
    """Fail-closed canary failure."""


@dataclass(frozen=True)
class Attempt:
    """One transport attempt (for the audit record)."""
    status: Optional[int]
    error: Optional[str]
    waited_s: float


@dataclass
class LiveTransport:
    """Minimal live transport honouring the frozen C3 retry policy.

    Five attempts = one initial + four retries; exponential backoff base 2 s capped at
    60 s; `Retry-After` honoured ONLY when the resulting wait plus the next attempt fit
    inside the 10-minute per-request window, else the policy is declared exhausted
    without sleeping past the window and without sending another request. Hard
    parameter/data-policy 4xx failures skip immediately (no retries).
    """
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    ca_file: Optional[str] = None
    attempts: list[Attempt] = field(default_factory=list)

    def _opener(self):
        if self.ca_file:
            import ssl
            ctx = ssl.create_default_context(cafile=self.ca_file)
            return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        return urllib.request.build_opener()

    def post(self, body: Mapping[str, Any], headers: Mapping[str, str],
             timeout: float = 60.0) -> tuple[int, dict, str]:
        started = self.clock()
        opener = self._opener()
        data = json.dumps(body).encode()
        last: tuple[int, dict, str] | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            req = urllib.request.Request(API_URL, data=data, method="POST")
            for h, v in headers.items():
                req.add_header(h, v)
            try:
                with opener.open(req, timeout=timeout) as resp:
                    self.attempts.append(Attempt(resp.status, None, 0.0))
                    return resp.status, dict(resp.headers), resp.read().decode()
            except urllib.error.HTTPError as e:
                raw = e.read().decode()
                hdrs = dict(e.headers)
                last = (e.code, hdrs, raw)
                self.attempts.append(Attempt(e.code, raw[:200], 0.0))
                if not _is_transient(e.code):
                    return last                      # hard 4xx: skip immediately
            except Exception as e:                    # transport-level failure
                last = (0, {}, f"{type(e).__name__}: {e}")
                self.attempts.append(Attempt(None, str(e)[:200], 0.0))

            if attempt == MAX_ATTEMPTS:
                break
            wait = min(BACKOFF_BASE_S * (2 ** (attempt - 1)), BACKOFF_CAP_S)
            ra = _retry_after(last[1]) if last else None
            if ra is not None:
                wait = max(wait, ra)                  # a shorter header never shrinks backoff
            elapsed = self.clock() - started
            if elapsed + wait >= REQUEST_WINDOW_S:
                break                                 # exhausted; never sleep past the window
            self.sleep(wait)
        if last is None:
            raise CanaryError("transport produced no response and no error")
        return last


def _is_transient(status: int) -> bool:
    return status == 429 or status == 408 or 500 <= status < 600


def _retry_after(headers: Mapping[str, str]) -> Optional[float]:
    for k, v in (headers or {}).items():
        if k.lower() == "retry-after":
            try:
                return max(0.0, float(v))
            except (TypeError, ValueError):
                return None
    return None


@dataclass(frozen=True)
class CanaryResult:
    model: str
    tag: str
    http_status: int
    cost_usd: Optional[float]
    content: Optional[str]
    finish_reason: Optional[str]
    reasoning_tokens: Optional[int]
    audit_ok: bool
    audit_failures: tuple[str, ...]
    reasoning_ok: bool
    reasoning_failures: tuple[str, ...]
    parse_ok: bool
    parse_reason: str
    reused: bool
    error: Optional[str]

    @property
    def passed(self) -> bool:
        # R-C6: the wire-format claim is only meaningful if the ANSWER parses under the
        # frozen anchored rule. Without this the live canary is weaker than the promotion
        # gate it feeds, and empty/prose/out-of-range content would pass.
        return (self.http_status == 200 and self.audit_ok and self.reasoning_ok
                and self.parse_ok and self.cost_usd is not None and self.error is None)


def canary_messages() -> list[dict]:
    return [{"role": "system", "content": CANARY_SYSTEM},
            {"role": "user", "content": CANARY_USER}]


def run_one(*, model: str, tag: str, key: str, snapshot: E.Snapshot,
            store: L.EnvelopeStore, ledger: L.V7Ledger,
            transport: LiveTransport) -> CanaryResult:
    """One synthetic canary call, persisted and accounted before any validation."""
    body, draw = planned_draw(model, tag)

    # R-C1: a persisted draw is REPLAYED FROM ITS RECORD, never assumed successful. The
    # prior DeepSeek 404 envelope must stay a failure on restart; the existence of a file
    # is not evidence of success.
    existing = store.get(draw.draw_id)
    if existing is not None:
        if existing.request_sha256 != draw.request_sha256:
            raise CanaryError(
                f"persisted envelope {draw.draw_id} has request hash "
                f"{existing.request_sha256} != recomputed {draw.request_sha256}")
        return _evaluate(model, tag, status=existing.http_status,
                         response=existing.response_body or {},
                         resp_headers=existing.response_headers or {},
                         cost=existing.cost_usd, snapshot=snapshot,
                         err=None if existing.cost_usd is not None else "cost_unreconciled",
                         reused=True)

    headers = E.request_headers(key)
    ledger.check_before_call(0.01, label=f"{STAGE}:{model}@{tag}")

    status, resp_headers, raw = transport.post(body, headers)
    try:
        response = json.loads(raw)
    except json.JSONDecodeError:
        response = {"_unparseable_body": raw}

    # R-C3: EVERY returned response goes through record_response — persist first, then book
    # any finite returned cost, regardless of HTTP status, audit, parse or cache outcome.
    # Some provider/error responses still incur prompt cost; validity is a separate question
    # from accounting.
    cost: Optional[float] = None
    err: Optional[str] = None
    try:
        recorded = L.record_response(
            store=store, ledger=ledger, draw=draw, request_body=body,
            request_headers=headers, response_body=response,
            response_headers=resp_headers, http_status=status, bucket=BUCKET,
            model=model, provider=tag, stage=STAGE)
        cost = recorded.booked_cost_usd
    except L.CostAccountingError as e:
        err = f"CostAccountingError: {e}"      # envelope is durable; needs reconciliation
    except L.LedgerError as e:
        err = f"{type(e).__name__}: {e}"

    # S-F2 exclusion is a VALIDITY finding, recorded separately from accounting.
    try:
        L.reject_cache_hit(response, resp_headers)
    except L.CacheHitRejected as e:
        err = f"CacheHitRejected: {e}"

    result = _evaluate(model, tag, status=status, response=response,
                       resp_headers=resp_headers, cost=cost, snapshot=snapshot,
                       err=err, reused=False)
    _write_derived(store, draw, result, status, err, cost)
    return result


def _write_derived(store: L.EnvelopeStore, draw: L.DrawIdentity, result: "CanaryResult",
                   status: int, err: Optional[str], cost: Optional[float]) -> None:
    """Linked derived validation record (R-E1/R-C3): why a paid call was excluded."""
    env = store.get(draw.draw_id)
    if env is None:
        return
    failures = tuple(f for f in (
        *(("http_error",) if status != 200 else ()),
        *(f"audit:{x}" for x in result.audit_failures),
        *(f"reasoning:{x}" for x in result.reasoning_failures),
        *((f"parse:{result.parse_reason}",) if not result.parse_ok else ()),
        *((f"error:{err}",) if err else ()),
    ))
    store.put_derived(L.DerivedRecord(
        draw_id=draw.draw_id,
        raw_sha256=L.canonical_sha256(env.response_body or {}),
        valid=result.passed, failures=failures,
        excluded_from_estimands=not result.passed,
        booked_cost_usd=cost if cost is not None else 0.0,
        timestamp=env.timestamp))


def planned_draw(model: str, tag: str) -> tuple[dict, L.DrawIdentity]:
    """The single authorized canary draw for one model/endpoint (pure)."""
    body = E.build_sampling_request(model, tag, canary_messages())
    sha = E.canonical_request_sha256(body)
    return body, L.DrawIdentity(request_sha256=sha, draw_index=0)


def _evaluate(model: str, tag: str, *, status: int, response: Mapping[str, Any],
              resp_headers: Mapping[str, Any], cost: Optional[float],
              snapshot: E.Snapshot, err: Optional[str], reused: bool) -> CanaryResult:
    """Derive the capability verdict from a response (pure; no I/O, no fabrication)."""
    if status != 200:
        return CanaryResult(model, tag, status, cost, None, None, None,
                            False, ("http_error",), False, ("http_error",),
                            False, "http_error", reused, err)

    audit = E.verify_provider_audit(response, model, tag, snapshot)
    reasoning = E.verify_reasoning_off(response)
    choice = (response.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = response.get("usage") or {}
    rt = ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))
    content = msg.get("content")

    # R-C6: the frozen anchored parser, plus the exact digit this prompt requests.
    pr = I.parse_option(content)
    parse_ok = bool(pr.ok and pr.option == EXPECTED_OPTION)
    parse_reason = ("ok" if parse_ok else
                    (pr.reason if not pr.ok else f"unexpected_option_{pr.option}"))

    return CanaryResult(
        model=model, tag=tag, http_status=status, cost_usd=cost,
        content=content, finish_reason=choice.get("finish_reason"),
        reasoning_tokens=rt,
        parse_ok=parse_ok, parse_reason=parse_reason,
        audit_ok=bool(getattr(audit, "ok", False)),
        audit_failures=tuple(getattr(audit, "failures", ()) or ()),
        reasoning_ok=bool(getattr(reasoning, "ok", False)),
        reasoning_failures=tuple(getattr(reasoning, "failures", ()) or ()),
        reused=reused, error=err)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--i-have-authorized-paid-spend", action="store_true", dest="ack",
                    help="required acknowledgement that this makes PAID OpenRouter calls")
    ap.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    ap.add_argument("--ca-file", default=None)
    ap.add_argument("--models", default=None,
                    help="comma-separated model slugs (default: the frozen panel order)")
    args = ap.parse_args(argv)

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return 2
    if not args.ack:
        print("This makes PAID OpenRouter calls. Re-run with --i-have-authorized-paid-spend",
              file=sys.stderr)
        return 2

    snapshot = E.load_snapshot(ROOT / E.SNAPSHOT_PATH)
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    store = L.EnvelopeStore(run_dir)

    rec = L.reconcile_prior_spend([d for d in PRIOR_RECORD_DIRS if d.exists()],
                                  non_reconciled=list(PRIOR_DIAGNOSTIC_COMPONENTS))

    models = ([m.strip() for m in args.models.split(",")] if args.models
              else list(PANEL_ORDER))

    # R-C2: bind the authorized canary draws and RECONSTRUCT current-run spend from the
    # store BEFORE the first budget check. Opening a fresh zeroed ledger silently dropped
    # every already-persisted v7 cost on restart.
    planned = {m: planned_draw(m, FALLBACK_SEQUENCES[m][0]) for m in models}
    draw_ids = frozenset(d.draw_id for _, d in planned.values())
    run_manifest = L.RunManifest(
        manifest_sha256=L.canonical_sha256(sorted(draw_ids)),
        draw_ids=draw_ids, model=",".join(models), endpoint="primary")
    ledger = L.reconstruct_ledger(store, manifest=run_manifest, reconciliation=rec)

    print(f"prior reconciled spend: ${rec.total_usd:.6f} (exact={rec.is_exact})")
    print(f"current-run spend already on disk: ${ledger.run_usd:.6f}")
    print(f"hard stop ${ledger.hard_stop_usd:.2f}; remaining ${ledger.remaining_usd:.4f}\n")

    transport = LiveTransport(ca_file=args.ca_file)

    results: list[CanaryResult] = []
    for model in models:
        tag = FALLBACK_SEQUENCES[model][0]     # PRIMARY endpoint only; no walk here
        r = run_one(model=model, tag=tag, key=key, snapshot=snapshot,
                    store=store, ledger=ledger, transport=transport)
        results.append(r)
        mark = "PASS" if r.passed else ("REUSED" if r.reused else "FAIL")
        print(f"### {model} @ {tag}  [{mark}]  HTTP {r.http_status}  cost={r.cost_usd}")
        print(f"    content={r.content!r} finish={r.finish_reason} "
              f"reasoning_tokens={r.reasoning_tokens}")
        if not r.audit_ok:
            print(f"    provider-audit FAIL: {r.audit_failures}")
        if not r.reasoning_ok:
            print(f"    reasoning-off FAIL: {r.reasoning_failures}")
        if not r.parse_ok:
            print(f"    anchored-parse FAIL: {r.parse_reason}")
        if r.error:
            print(f"    error: {r.error}")
        print()

    spent = ledger.run_usd
    print(f"=== canary run spend ${spent:.6f}; cumulative ${ledger.total_spent_usd:.6f} "
          f"of ${ledger.hard_stop_usd:.2f} (exact={ledger.is_exact}) ===")
    print(f"artifacts: {run_dir}")
    # R-C1: `reused` no longer implies success — a replayed record carries its REAL verdict,
    # so a persisted 404 stays a failure.
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
