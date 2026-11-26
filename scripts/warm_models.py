"""Load and check every model LumenEIOS uses, once the backend is up.  Started by run.bat.

  * Qwen2.5-VL (local, GPU)  - loaded by sending one tiny image through /ocr/extract-preview
  * Gemini (cloud fallback)  - only reported as configured / not configured; no request is sent
  * LLM provider             - reported from the backend settings

Uses the standard library only, so it runs in any of the project's Python environments.
Environment overrides: BACKEND_URL, WARMUP_USER, WARMUP_PASSWORD.
The default login is the documented local development root login (docs/LOGIN_CREDENTIALS.md);
it only works while APP_ENV=development.
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/v1"
USER = os.environ.get("WARMUP_USER", "LEOFELIX")
PASSWORD = os.environ.get("WARMUP_PASSWORD", "KVR")
APP_DIR = Path(__file__).resolve().parents[1]


def say(msg):
    print(f"[models] {msg}", flush=True)


def env_value(name):
    if os.environ.get(name):
        return os.environ[name]
    env_file = APP_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return ""


def wait_for_backend(seconds=180):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(BASE + "/openapi.json", timeout=3)
            return True
        except urllib.error.HTTPError:
            return True  # server answered
        except Exception:
            time.sleep(2)
    return False


def login():
    req = urllib.request.Request(
        BASE + "/auth/login",
        data=json.dumps({"email": USER, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("access_token", "")
    except Exception as exc:
        say(f"Login for warm-up failed ({exc}). Qwen will load on the first OCR request instead.")
        return ""


def warm_qwen(token):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        say("Pillow is missing - skipping the Qwen warm-up.")
        return
    img = Image.new("RGB", (360, 90), "white")
    ImageDraw.Draw(img).text((12, 34), "LumenEIOS model warm-up", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("provider", "qwen"), ("wait_before_each_image", "false")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(
        (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="warmup.png"\r\n'
         "Content-Type: image/png\r\n\r\n").encode() + buf.getvalue() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        BASE + "/ocr/extract-preview", data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Authorization": f"Bearer {token}"},
    )
    say("Loading Qwen2.5-VL onto the GPU (first load takes about 30-120 seconds)...")
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            data = json.load(r)
        say(f"Qwen READY: {data.get('model_version')} (loaded in {time.time() - started:.0f}s)")
    except urllib.error.HTTPError as exc:
        say(f"Qwen warm-up failed: HTTP {exc.code} {exc.read()[:300].decode(errors='ignore')}")
    except Exception as exc:
        say(f"Qwen warm-up failed: {exc}")


def main():
    say(f"Waiting for the backend at {BASE} ...")
    if not wait_for_backend():
        say("Backend did not come up within 3 minutes - check the backend window.")
        return 1
    token = login()
    if token:
        warm_qwen(token)
    gemini = env_value("GEMINI_API_KEY")
    say(f"Gemini fallback: {'API key configured (model ' + (env_value('GEMINI_MODEL') or 'default') + ')' if gemini else 'NOT configured - Qwen only'}")
    say(f"LLM provider: {env_value('LLM_PROVIDER') or 'deterministic'} | OCR provider: {env_value('ACTIVE_OCR_PROVIDER') or 'simulated'}")
    say("All set. You can close this window.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
