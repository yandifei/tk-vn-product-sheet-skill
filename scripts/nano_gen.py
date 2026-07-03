"""Image generation via nano-banana-2 (primary) — hfsyapi Gemini-style endpoint.

clean --image <url> [--size 4K] [--aspect 1:1]

Removes brand names/logos/watermarks and translates text to Vietnamese.
Supports 1K/2K/4K and up to 7 reference images. Returns hosted URL.

Auth: reads HFSY_API_KEY env var, falls back to assets/hfsy_key.txt.

Note: returned URLs are OSS signed links (~24h expiry). Upload to TikTok
promptly. Original source URL is preserved for regeneration if needed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://www.hfsyapi.cn/v1beta/models/nano-banana-2:generateContent"
TIMEOUT = 300
RETRIES = 3

PROMPT_FILE = Path(__file__).resolve().parent.parent / '图片生成提示词.md'

def _load_prompt() -> str:
    """Read the shared image-cleaning prompt from the project root markdown file."""
    text = PROMPT_FILE.read_text(encoding='utf-8')
    # The first line is '# 提示词'; everything after is the prompt body.
    _, _, body = text.partition('
')
    return body.lstrip('
')

PROMPT = _load_prompt()


def get_api_key() -> str:
    for name in ("HFSY_API_KEY", "NANO_API_KEY"):
        v = os.environ.get(name)
        if v:
            return v.strip()
    here = Path(__file__).resolve().parent.parent
    for fn in ("hfsy_key.txt", "nano_key.txt"):
        keyfile = here / "assets" / fn
        if keyfile.is_file():
            return keyfile.read_text(encoding="utf-8").strip()
    raise SystemExit("Missing API key. Set HFSY_API_KEY env var.")


def guess_mime(url: str) -> str:
    u = url.lower()
    if u.endswith(".png"):
        return "image/png"
    if u.endswith(".webp"):
        return "image/webp"
    if u.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def clean(image_urls: list[str], size: str, aspect: str) -> str:
    """Generate cleaned image. image_urls can be 1-7 reference images."""
    key = get_api_key()
    parts = [{"text": PROMPT}]
    for url in image_urls[:7]:
        parts.append({"fileData": {"mimeType": guess_mime(url), "fileUri": url}})
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"imageConfig": {"imageSize": size, "aspectRatio": aspect}},
    }
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(
                API_URL, data=body, method="POST",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json",
                         "User-Agent": "curl/7.68.0"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # extract fileUri from candidates
            for cand in data.get("candidates", []):
                for p in cand.get("content", {}).get("parts", []):
                    fd = p.get("fileData")
                    if fd and fd.get("fileUri"):
                        return fd["fileUri"]
            last_err = f"no fileUri in response: {json.dumps(data)[:200]}"
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            last_err = f"HTTP {e.code}: {msg[:200]}"
            if e.code in (429, 500, 502, 503):
                time.sleep(2 * attempt)
                continue
            break
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = str(e)
            time.sleep(2 * attempt)
    raise SystemExit(f"nano-banana-2 failed after {RETRIES} attempts: {last_err}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clean")
    c.add_argument("--image", required=True, action="append",
                   help="Image URL (repeat for up to 7 reference images)")
    c.add_argument("--size", default="4K", choices=["1K", "2K", "4K"])
    c.add_argument("--aspect", default="1:1")
    args = ap.parse_args(argv)

    if args.cmd == "clean":
        url = clean(args.image, args.size, args.aspect)
        if not url:
            print("__FAIL__")
            return 1
        print(url)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
