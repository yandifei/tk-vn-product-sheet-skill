"""Call the Agnes AI image generation API to clean a product image.

clean --image <url> [--vi-text <text>] [--size 2048x2048]

Removes brand names / logos / watermarks. Optionally redraws any text in the
image with provided Vietnamese text. Supports 2K resolution.

Auth: reads AGNES_API_KEY env var, falls back to assets/agnes_key.txt.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
MODEL = "agnes-image-2.1-flash"
TIMEOUT = 300
RETRIES = 3

BASE_PROMPT_FILE = Path(__file__).resolve().parent.parent / '图片生成提示词.md'

def _load_base_prompt() -> str:
    """Read the shared image-cleaning prompt from the project root markdown file."""
    text = BASE_PROMPT_FILE.read_text(encoding='utf-8')
    _, _, body = text.partition('
')
    return body.lstrip('
')

BASE_PROMPT = _load_base_prompt()
VI_PROMPT_TMPL = "\n【越南语文字指定】\n请将图片中的中文文案替换为以下越南语文字：\n{vi}"


def get_api_key() -> str:
    for name in ("AGNES_API_KEY", "AGNES_API_TOKEN", "APIHUB_AGNES_API_KEY"):
        v = os.environ.get(name)
        if v:
            return v.strip()
    # fallback to assets file
    here = Path(__file__).resolve().parent.parent
    keyfile = here / "assets" / "agnes_key.txt"
    if keyfile.is_file():
        return keyfile.read_text(encoding="utf-8").strip()
    raise SystemExit("Missing API key. Set AGNES_API_KEY or fill assets/agnes_key.txt")


def image_to_data_uri(url: str) -> str:
    """Pass http(s) URLs and data-URIs through; convert local files to a
    base64 data-URI so the API doesn't need to fetch the source."""
    if url.startswith(("http://", "https://", "data:")):
        return url
    p = Path(url)
    if p.is_file():
        raw = p.read_bytes()
        suffix = p.suffix.lower()
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif",
        }.get(suffix, "image/jpeg")
        return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
    return url


def build_prompt(vi_text: str | None) -> str:
    p = BASE_PROMPT
    if vi_text:
        p += VI_PROMPT_TMPL.format(vi=vi_text)
    return p


def request_json(payload: dict) -> dict:
    key = get_api_key()
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(2 * attempt)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            last_err = f"HTTP {e.code}: {msg[:200]}"
            if e.code in (503, 500, 429):
                time.sleep(2 * attempt)
                continue
            break
    raise SystemExit(f"agnes request failed after {RETRIES} attempts: {last_err}")


def extract_url(data: dict) -> str:
    if isinstance(data.get("url"), str):
        return data["url"]
    if isinstance(data.get("image_url"), str):
        return data["image_url"]
    if isinstance(data.get("data"), list):
        for item in data["data"]:
            if isinstance(item, dict):
                for k in ("url", "image_url"):
                    if isinstance(item.get(k), str):
                        return item[k]
    return ""


def clean(image_url: str, vi_text: str | None, size: str) -> str:
    prompt = build_prompt(vi_text)
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "extra_body": {
            "image": [image_to_data_uri(image_url)],
            "response_format": "url",
        },
    }
    if size:
        payload["size"] = size
    data = request_json(payload)
    url = extract_url(data)
    return url


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clean")
    c.add_argument("--image", required=True)
    c.add_argument("--vi-text", default=None)
    c.add_argument("--size", default="1024x1024")
    args = ap.parse_args(argv)

    if args.cmd == "clean":
        url = clean(args.image, args.vi_text, args.size)
        if not url:
            print("__FAIL__")
            return 1
        print(url)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
