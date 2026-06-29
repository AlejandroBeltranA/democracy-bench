"""Redirect Inspect AI's log/trace writes into a temp dir so the suite runs in sandboxes
that can't write to the user app-data dir (~/Library/Application Support/inspect_ai/...).
Set at import time, before any test imports inspect_ai. Honoured only if not already set."""
import os
import tempfile

_base = os.path.join(tempfile.gettempdir(), "democracy_bench_inspect")
os.makedirs(os.path.join(_base, "logs"), exist_ok=True)
os.environ.setdefault("INSPECT_LOG_DIR", os.path.join(_base, "logs"))
os.environ.setdefault("INSPECT_TRACE_FILE", os.path.join(_base, "trace.log"))
