"""Image edit via gpt-image-2 /v1/images/edits endpoint (better preservation).

edit --image <url> [--size 1024x1024]

Uses the OpenAI-style image *edit* endpoint (multipart form-data) instead of
generations. Edit mode keeps the original product closer to the source than
full text-to-image regeneration. Removes brand/logo/watermark and translates
text to Vietnamese.

NOTE: This is NOT true pixel-level mask inpainting — gpt-image-2 has no mask
support here, so removal/translation is still best-effort (but better preserved
than full regeneration). For hard watermarks on complex backgrounds, results
may still be imperfect.

Auth: HFSY_API_KEY env var, falls back to assets/hfsy_key.txt.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API_URL = "https://www.hfsyapi.cn/v1/images/edits"
MODEL = "gpt-image-2"
TIMEOUT = 300

PROMPT = "Remove brand names, logos and watermarks. Translate all text to Vietnamese. Keep the product exactly the same."


def get_api_key() -> str:
    for name in ("HFSY_API_KEY", "NANO_API_KEY"):
        v = os.environ.get(name)
        if v:
            return v.strip()
    here = Path(__file__).resolve().parent.parent
    for fn in ("hfsy_key.txt", "nano_key.txt"):
        kf = here / "assets" / fn
        if kf.is_file():
            return kf.read_text(encoding="utf-8").strip()
    raise SystemExit("Missing API key. Set HFSY_API_KEY env var.")


def _download(url: str) -> bytes:
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _multipart(fields: dict[str, str], img_bytes: bytes,
               img_field: str = "image", filename: str = "image.jpg") -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()
    for name, value in fields.items():
        buf.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    buf.write(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{img_field}"; '
        f'filename="{filename}"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
        + img_bytes + b"\r\n"
    )
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), boundary


def edit(image_url_or_path: str, size: str) -> str:
    key = get_api_key()
    # get image bytes (URL or local path)
    p = Path(image_url_or_path)
    if p.is_file():
        img = p.read_bytes()
    else:
        img = _download(image_url_or_path)
    body, boundary = _multipart(
        {"model": MODEL, "prompt": PROMPT, "size": size, "response_format": "url"},
        img,
    )
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "curl/7.68.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("data", []):
            if item.get("url"):
                return item["url"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"edits HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}")
    return ""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("edit")
    c.add_argument("--image", required=True, help="Image URL or local path")
    c.add_argument("--size", default="1024x1024")
    args = ap.parse_args(argv)

    if args.cmd == "edit":
        url = edit(args.image, args.size)
        if not url:
            print("__FAIL__")
            return 1
        print(url)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
