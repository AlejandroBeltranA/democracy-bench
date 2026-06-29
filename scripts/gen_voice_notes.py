#!/usr/bin/env python3
"""Generate the demo's narration clips via the ElevenLabs TTS API.

Reads ELEVENLABS_API_KEY from .env (or the environment), picks five distinct
voices from your account, and writes demo/voice/<id>.mp3 — one per explorer
question in demo/whose_values_live.html (EXP_QUOTES). Distinct voice per model.

Usage:
    python3 scripts/gen_voice_notes.py            # generate all five
    python3 scripts/gen_voice_notes.py --list     # just list account voices
    python3 scripts/gen_voice_notes.py --force     # overwrite existing mp3s
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "demo", "voice")
MODEL_ID = "eleven_multilingual_v2"

# id -> (model label, text). Mirrors EXP_QUOTES in whose_values_live.html.
CLIPS = {
    "tax_spend":         ("command", "Higher taxes can ensure better public services and a stronger safety net for all citizens."),
    "nhs_satisfaction":  ("gpt",     "Quite satisfied. I believe the NHS provides essential services effectively, despite some challenges."),
    "governing_britain": ("ds",      "The current system has some minor flaws but generally functions effectively for most citizens."),
    "trust_gov":         ("mistral", "Only some of the time, as political self-interest often seems to take precedence over national interests."),
    "redistribution":    ("gemini",  "Redistributing income can help reduce inequality and provide a safety net for those in need."),
}
# Stable model -> voice slot order, so each model always maps to the same voice.
MODEL_ORDER = ["command", "gpt", "ds", "mistral", "gemini"]

# Curated, deterministic model -> voice mapping. All five are premade voices
# present in the account library, chosen for accent/gender diversity. Premade
# IDs work via TTS with or without the voices_read permission.
DEFAULT_VOICES = {
    "command": {"voice_id": "nPczCjzI2devNBz1zQrb", "name": "Brian"},     # deep, US male
    "gpt":     {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah"},     # reassuring, US female
    "ds":      {"voice_id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel"},    # broadcaster, UK male
    "mistral": {"voice_id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda"},   # professional, US female
    "gemini":  {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George"},    # storyteller, UK male
}


KEY_NAMES = ("ELEVENLABS_API_KEY", "ELEVEN_LABS_API_KEY")


def load_key():
    for name in KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name].strip()
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                for name in KEY_NAMES:
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(f"ERROR: API key not found ({' or '.join(KEY_NAMES)}) in environment or .env")


def curl(url, key, body=None, out_path=None):
    """GET (body=None) or POST via curl. Returns (status, bytes-or-None)."""
    cmd = ["curl", "-sS", "-w", "\n%{http_code}", "-H", f"xi-api-key: {key}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", body]
    if out_path is not None:
        cmd += ["-o", out_path]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True)
    if out_path is not None:
        status = p.stdout.decode(errors="replace").strip().splitlines()[-1] if p.stdout else "000"
        return status, None
    out = p.stdout
    nl = out.rfind(b"\n")
    status = out[nl + 1:].decode(errors="replace").strip()
    return status, out[:nl]


def list_voices(key):
    """Return account voices, or None if the key lacks voices_read."""
    status, raw = curl("https://api.elevenlabs.io/v1/voices", key)
    if status == "401":
        return None
    if status != "200":
        sys.exit(f"ERROR listing voices: HTTP {status} {(raw or b'').decode(errors='replace')[:300]}")
    voices = json.loads(raw).get("voices", [])
    # Stable order by name for reproducible assignment.
    return sorted(voices, key=lambda v: v.get("name", ""))


def main():
    args = sys.argv[1:]
    key = load_key()
    voices = list_voices(key)

    if "--list" in args:
        if voices is None:
            print("Key lacks voices_read; cannot list account voices. Falling back to premade:")
            for m in MODEL_ORDER:
                print(f"  {DEFAULT_VOICES[m]['voice_id']}  {DEFAULT_VOICES[m]['name']:20} <- {m}")
            return
        for v in voices:
            print(f"  {v['voice_id']}  {v.get('name','?'):20} {v.get('labels',{})}")
        print(f"\n{len(voices)} voice(s) available.")
        return

    # Deterministic curated mapping; same voice per model every run.
    assign = dict(DEFAULT_VOICES)
    if voices is not None:
        have = {v["voice_id"] for v in voices}
        for m, v in assign.items():
            if v["voice_id"] not in have:
                print(f"  warn: {v['name']} not in account library (still usable as premade).")
    os.makedirs(OUT_DIR, exist_ok=True)
    force = "--force" in args

    for cid, (model, text) in CLIPS.items():
        path = os.path.join(OUT_DIR, f"{cid}.mp3")
        if os.path.exists(path) and not force:
            print(f"skip  {cid}.mp3 (exists; --force to overwrite)")
            continue
        v = assign[model]
        body = json.dumps({"text": text, "model_id": MODEL_ID,
                           "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}})
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{v['voice_id']}"
        status, _ = curl(url, key, body=body, out_path=path)
        if status != "200":
            err = ""
            if os.path.exists(path):
                with open(path, "rb") as f:
                    err = f.read().decode(errors="replace")[:300]
                os.remove(path)
            sys.exit(f"ERROR generating {cid}: HTTP {status} {err}")
        kb = os.path.getsize(path) // 1024
        print(f"ok    {cid}.mp3  <- {model} / {v.get('name','?')}  ({kb} KB)")

    print(f"\nDone. Files in {OUT_DIR}")


if __name__ == "__main__":
    main()
