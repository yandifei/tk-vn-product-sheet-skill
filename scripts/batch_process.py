"""Parallel batch image processor — fast mode (agent-cluster-like concurrency).

Usage:
  python scripts/batch_process.py "<xlsx>" [--doubao-key KEY] [--hfsy-key KEY] [--agnes-key KEY]
  Optional: --audit-workers 12  --gen-workers 8  --gen-size 4K

Pipeline:
  1. prepare (deterministic: brand/stock/SKU/video)
  2. Vision audit all unique images (N parallel) → structured JSON per image
  3. Batch image gen for brand/logo/watermark/text only
     (M parallel, nano-banana-2 → Doubao → GPT-Image-2 fallback chain)
  4. Share main/sub URLs to all variant rows
  5. finalize (write all results)

Concurrency = Python ThreadPoolExecutor (no agent runtime needed, open-source
friendly). The bottleneck is API wait time (image gen 30-60s each), so N
concurrent requests give near-linear speedup.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_pipeline  # noqa: E402
from run_pipeline import prepare as rp_prepare, finalize as rp_finalize

PROMPT = "Remove brand names, logos and watermarks from the image, and translate all text to Vietnamese."

AUDIT_SYSTEM = (
    "Audit product image. Output JSON only: "
    '{"has_brand_name":bool,"brand_names_found":[],"has_logo":bool,'
    '"has_watermark":bool,"has_chinese_text":bool,"is_promo_banner":bool,'
    '"needs_cleaning":bool,"cleaning_reason":"brand|logo|watermark|text|promo|none"}'
)


# ── API call helpers ──────────────────────────────────────


def vision_audit(url: str, agnes_key: str, timeout: int = 60,
                 ark_key: str = "") -> dict:
    """Audit a single image by URL. No local download — sends URL directly.
    Primary: minimax-m3 via Volcengine coding endpoint (better recall on
    brand/logo/watermark). Fallback: Agnes 2.0 flash. Returns structured dict.
    """
    # --- Primary: minimax-m3 (Volcengine) ---
    if ark_key:
        try:
            resp = requests.post(
                "https://ark.cn-beijing.volces.com/api/coding/v1/chat/completions",
                headers={"Authorization": f"Bearer {ark_key}"},
                json={
                    "model": "minimax-m3",
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": AUDIT_SYSTEM + "\nBe thorough: check every corner for small logos, semi-transparent watermarks, tiny brand marks."},
                        {"type": "image_url", "image_url": {"url": url}}
                    ]}],
                    "max_tokens": 500,
                },
                timeout=timeout,
            )
            content = resp.json()["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if m:
                d = json.loads(m.group(0))
                if "needs_cleaning" in d or "has_brand_name" in d:
                    return d
        except Exception:
            pass
    # --- Fallback: Agnes 2.0 flash ---
    try:
        resp = requests.post(
            "https://apihub.agnes-ai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {agnes_key}"},
            json={
                "model": "agnes-2.0-flash",
                "messages": [
                    {"role": "system", "content": AUDIT_SYSTEM},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Audit this image for brand names, logos, watermarks, or Chinese text. Be thorough."},
                        {"type": "image_url", "image_url": {"url": url}}
                    ]}
                ],
                "max_tokens": 400,
            },
            timeout=timeout,
        )
        content = resp.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    # On total failure, conservatively assume needs cleaning (safer for IP)
    return {"needs_cleaning": True, "cleaning_reason": "unknown", "is_promo_banner": False}


def _to_data_uri(url: str) -> str | None:
    """Download image and return base64 data URI (for gw.alicdn that blocks API fetch)."""
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return f"data:image/jpeg;base64,{base64.b64encode(r.content).decode()}"
    except Exception:
        pass
    return None


def nano_gen(url: str, key: str, size: str = "4K", timeout: int = 300) -> str | None:
    """Primary: nano-banana-2 (up to 4K). Returns URL or None."""
    try:
        img_uri = url
        if "gw.alicdn" in url:
            img_uri = _to_data_uri(url) or url
        resp = requests.post(
            "https://www.hfsyapi.cn/v1beta/models/nano-banana-2:generateContent",
            headers={"Authorization": f"Bearer {key}", "User-Agent": "curl/7.68.0"},
            json={
                "contents": [{"parts": [
                    {"text": PROMPT},
                    {"fileData": {"mimeType": "image/jpeg", "fileUri": img_uri}}
                ]}],
                "generationConfig": {"imageConfig": {"imageSize": size, "aspectRatio": "1:1"}},
            },
            timeout=timeout,
        )
        data = resp.json()
        for cand in data.get("candidates", []):
            for p in cand.get("content", {}).get("parts", []):
                fd = p.get("fileData")
                if fd and fd.get("fileUri"):
                    return fd["fileUri"]
    except Exception:
        pass
    return None


def doubao_gen(url: str, key: str, size: str = "2K", timeout: int = 180) -> str | None:
    """Fallback 1: Doubao Seedream 5.0. Returns URL or None."""
    try:
        resp = requests.post(
            "https://ark.cn-beijing.volces.com/api/v3/images/generations",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "doubao-seedream-5-0-260128",
                "prompt": PROMPT,
                "image": url,
                "response_format": "url",
                "size": size,
                "watermark": False,
            },
            timeout=timeout,
        )
        return resp.json()["data"][0]["url"]
    except Exception:
        return None


def hfsyapi_gen(url: str, key: str, timeout: int = 300) -> str | None:
    """Fallback 2: GPT-Image-2 via hfsyapi (1K). Returns URL or None."""
    try:
        ref = url
        if "gw.alicdn" in url:
            ref = _to_data_uri(url) or url
        resp = requests.post(
            "https://www.hfsyapi.cn/v1/images/generations",
            headers={"Authorization": f"Bearer {key}", "User-Agent": "curl/7.68.0"},
            json={
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "reference_images": [ref],
                "size": "1024x1024",
                "n": 1,
                "response_format": "url",
            },
            timeout=timeout,
        )
        return resp.json()["data"][0]["url"]
    except Exception:
        return None


def edit_gen(url: str, key: str, timeout: int = 300) -> str | None:
    """Primary: gpt-image-2 /v1/images/edits (multipart, best product preservation).
    Edit mode keeps original closer than full regeneration. Returns URL or None."""
    try:
        import io
        import uuid
        img = requests.get(url if url.startswith("http") else "https:" + url,
                           timeout=60, headers={"User-Agent": "Mozilla/5.0"}).content
        boundary = uuid.uuid4().hex
        buf = io.BytesIO()
        for n, v in {"model": "gpt-image-2", "prompt": PROMPT,
                     "size": "1024x1024", "response_format": "url"}.items():
            buf.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n'.encode())
        buf.write(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
                  f'filename="i.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode() + img + b"\r\n")
        buf.write(f"--{boundary}--\r\n".encode())
        resp = requests.post(
            "https://www.hfsyapi.cn/v1/images/edits",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": f"multipart/form-data; boundary={boundary}",
                     "User-Agent": "curl/7.68.0"},
            data=buf.getvalue(), timeout=timeout,
        )
        return resp.json()["data"][0]["url"]
    except Exception:
        return None


# ── Main pipeline ─────────────────────────────────────────


def auto_process(xlsx_path: str, ark_key: str, hfsy_key: str, agnes_key: str,
                 work_path: str | None = None, audit_workers: int = 12,
                 gen_workers: int = 8, gen_size: str = "4K") -> dict[str, Any]:
    xlsx = Path(xlsx_path).resolve()
    work = Path(work_path or xlsx.with_name("work_auto.json")).resolve()

    # Step 1: prepare (fast, <1s)
    print("[1/5] Prepare (deterministic transforms)...", flush=True)
    rp_prepare(str(xlsx), str(work))
    w = json.loads(work.read_text(encoding="utf-8"))

    # Collect unique image URLs (dedup — 94 rows x 12 imgs -> ~120 unique)
    unique_urls: dict[str, dict] = {}
    for row in w["rows"]:
        for img in row["images"]:
            url = img["orig"]
            if url and url not in unique_urls:
                unique_urls[url] = img
    all_urls = list(unique_urls.keys())
    print(f"   {len(all_urls)} unique images across {len(w['rows'])} rows", flush=True)

    # Step 2: Vision audit (parallel — cluster-like)
    print(f"[2/5] Vision audit ({audit_workers} parallel)...", flush=True)
    audits: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=audit_workers) as ex:
        fut = {ex.submit(vision_audit, url, agnes_key, 60, ark_key): url for url in all_urls}
        for f in as_completed(fut):
            audits[fut[f]] = f.result()

    def classify(a: dict, source: str) -> str:
        """Classify an image. `delete` ONLY applies to desc(C) column images.
        Main/sub/variant images are never deleted — only cleaned or kept."""
        needs_clean = (a.get("needs_cleaning") or a.get("has_brand_name")
                       or a.get("has_logo") or a.get("has_watermark")
                       or a.get("has_chinese_text"))
        if source == "desc":
            # description column: unrelated promo/service imgs can be deleted
            if a.get("is_promo_banner"):
                return "delete"
            return "regen" if needs_clean else "keep"
        else:
            # main / sub / variant: NEVER delete, only clean or keep
            return "regen" if needs_clean else "keep"

    # a url may appear in multiple columns; a url used ONLY in desc can be
    # deleted, but if the same url is also a main/sub/variant image it must
    # not be deleted. Track the "strongest" source per url (non-desc wins).
    url_source: dict[str, str] = {}
    for row in w["rows"]:
        for img in row["images"]:
            u, s = img["orig"], img.get("source", "desc")
            if u not in url_source or url_source[u] == "desc":
                url_source[u] = s  # non-desc source overrides desc

    decisions = {url: classify(audits.get(url, {}), url_source.get(url, "desc"))
                 for url in all_urls}
    n_del = sum(1 for d in decisions.values() if d == "delete")
    n_regen = sum(1 for d in decisions.values() if d == "regen")
    n_keep = sum(1 for d in decisions.values() if d == "keep")
    print(f"   delete(desc only)={n_del} regen={n_regen} keep={n_keep}", flush=True)

    # Step 3: Generate only for regen (parallel, fallback chain)
    to_gen = [u for u in all_urls if decisions.get(u) == "regen"]
    print(f"[3/5] Image gen for {len(to_gen)} images ({gen_workers} parallel)...", flush=True)
    gen_results: dict[str, str | None] = {}

    def gen_one(url: str) -> tuple[str, str | None]:
        # edits (best preservation) → nano-banana-2(4K) → Doubao(2K) → GPT generations(1K)
        if hfsy_key:
            r = edit_gen(url, hfsy_key)
            if r:
                return url, r
        if hfsy_key:
            r = nano_gen(url, hfsy_key, size=gen_size)
            if r:
                return url, r
        if ark_key:
            r = doubao_gen(url, ark_key)
            if r:
                return url, r
        if hfsy_key:
            r = hfsyapi_gen(url, hfsy_key)
            if r:
                return url, r
        return url, None

    with ThreadPoolExecutor(max_workers=gen_workers) as ex:
        fut = {ex.submit(gen_one, url): url for url in to_gen}
        for f in as_completed(fut):
            _, new_url = f.result()
            gen_results[fut[f]] = new_url

    gen_ok = sum(1 for v in gen_results.values() if v)
    gen_fail = sum(1 for v in gen_results.values() if not v)
    print(f"   generated {gen_ok} OK, {gen_fail} failed (kept original)", flush=True)

    # Apply results to work.json (per-image, respecting source column)
    for row in w["rows"]:
        for img in row["images"]:
            url = img["orig"]
            src = img.get("source", "desc")
            d = decisions.get(url, "keep")
            # Safety: delete only ever applies to desc images
            if d == "delete" and src != "desc":
                d = "regen" if gen_results.get(url) else "keep"
            if d == "delete":
                img["decision"] = "delete"
            elif d == "regen":
                new_url = gen_results.get(url)
                if new_url:
                    img["decision"] = "regen"
                    img["new_url"] = new_url
                else:
                    img["decision"] = "keep"  # gen failed, keep original
                    img["new_url"] = ""
            else:
                img["decision"] = "keep"
                img["new_url"] = ""

    work.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   saved {work}", flush=True)

    # Step 5: Finalize
    print("[4/5] Finalize (writing sheet)...", flush=True)
    rp_finalize(str(xlsx), str(work), str(xlsx))
    print("[5/5] Done!", flush=True)

    return {
        "rows": len(w["rows"]),
        "unique_images": len(all_urls),
        "delete": n_del, "regen": n_regen, "keep": n_keep,
        "generated_ok": gen_ok, "generated_fail": gen_fail,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Auto batch process TikTok Vietnam product sheet")
    ap.add_argument("xlsx", help="Path to xlsx file")
    ap.add_argument("--doubao-key", default=os.environ.get("ARK_API_KEY", ""))
    ap.add_argument("--hfsy-key", default=os.environ.get("HFSY_API_KEY", ""))
    ap.add_argument("--agnes-key", default=os.environ.get("AGNES_API_KEY", ""))
    ap.add_argument("--work", default=None)
    ap.add_argument("--audit-workers", type=int, default=12, help="parallel vision audits")
    ap.add_argument("--gen-workers", type=int, default=8, help="parallel image generations")
    ap.add_argument("--gen-size", default="4K", choices=["1K", "2K", "4K"])
    args = ap.parse_args(argv)

    print("=== TK-VN Product Sheet Auto Processor ===", flush=True)
    print(f"Input: {args.xlsx}", flush=True)
    print(f"nano-banana-2/GPT-Image-2: {'ok' if args.hfsy_key else 'MISSING'}  "
          f"Doubao: {'ok' if args.doubao_key else 'MISSING'}  "
          f"Vision: {'ok' if args.agnes_key else 'MISSING'}", flush=True)
    print(f"Concurrency: audit={args.audit_workers} gen={args.gen_workers} size={args.gen_size}\n", flush=True)

    report = auto_process(args.xlsx, args.doubao_key, args.hfsy_key, args.agnes_key,
                          args.work, args.audit_workers, args.gen_workers, args.gen_size)
    print("\n=== Summary ===", flush=True)
    for k, v in report.items():
        print(f"  {k}: {v}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

