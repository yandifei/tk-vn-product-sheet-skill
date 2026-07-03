# Recipes — Batch Processing Code

## Parallel batch processing (Python)

```python
import requests, json, concurrent.futures

AGNES_KEY = "..."  # vision audit
ARK_KEY = "..."    # Doubao image gen
HFSY_KEY = "..."   # fallback image gen

# PROMPT is now read from the project-root 图片生成提示词.md at runtime.
# To change the prompt, edit that file — all generation scripts pick it up automatically.
PROMPT = Path(__file__).resolve().parent.parent / "图片生成提示词.md"  # read at call site

def audit_image(url):
    """Vision audit: returns JSON with has_brand_name, has_logo, has_watermark, has_chinese_text, is_promo_banner, needs_cleaning"""
    resp = requests.post("https://apihub.agnes-ai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {AGNES_KEY}"},
        json={"model":"agnes-2.0-flash","messages":[
            {"role":"system","content":'Audit image. Output JSON: {"has_brand_name":bool,"has_logo":bool,"has_watermark":bool,"has_chinese_text":bool,"is_promo_banner":bool,"needs_cleaning":bool,"cleaning_reason":"brand|logo|watermark|text|promo|none"}'},
            {"role":"user","content":[{"type":"text","text":"Audit for brand/logo/watermark/Chinese text."},{"type":"image_url","image_url":{"url":url}}]}
        ],"max_tokens":400})
    import re
    c = resp.json()["choices"][0]["message"]["content"]
    m = re.search(r'\{.*\}', c, re.DOTALL)
    return json.loads(m.group(0)) if m else {}

def gen_image_doubao(url):
    """Doubao Seedream 5.0: returns cleaned image URL (2K)"""
    resp = requests.post("https://ark.cn-beijing.volces.com/api/v3/images/generations",
        headers={"Authorization": f"Bearer {ARK_KEY}"},
        json={"model":"doubao-seedream-5-0-260128","prompt":PROMPT,
              "image": url, "response_format":"url", "size":"2K","watermark":False},
        timeout=180)
    return resp.json()["data"][0]["url"]

def gen_image_hfsy(url):
    """Fallback: GPT-Image-2 via hfsyapi (1K)"""
    resp = requests.post("https://www.hfsyapi.cn/v1/images/generations",
        headers={"Authorization": f"Bearer {HFSY_KEY}","User-Agent":"curl/7.68.0"},
        json={"model":"gpt-image-2","prompt":PROMPT,"reference_images":[url],
              "size":"1024x1024","n":1,"response_format":"url"},
        timeout=300)
    return resp.json()["data"][0]["url"]

def process_one(url):
    """Audit + generate if needed. Returns (url, new_url_or_None, decision)."""
    audit = audit_image(url)
    if audit.get("is_promo_banner"):
        return url, None, "delete"
    if not audit.get("needs_cleaning"):
        return url, None, "keep"
    # needs cleaning — try Doubao then hfsyapi
    try:
        return url, gen_image_doubao(url), "regen"
    except Exception:
        try:
            return url, gen_image_hfsy(url), "regen"
        except Exception:
            return url, None, "keep"  # fallback to original

# Deduplicate URLs across all rows (94 rows × 12 imgs → ~120 unique)
unique_urls = list({img["orig"] for row in work["rows"] for img in row["images"]})

# Parallel: 10 concurrent audits + 5 concurrent generations
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(process_one, unique_urls))

# Apply results back to work.json
url_map = {r[0]: (r[1], r[2]) for r in results}
for row in work["rows"]:
    for img in row["images"]:
        new_url, decision = url_map.get(img["orig"], (None, "keep"))
        img["decision"] = decision
        if new_url:
            img["new_url"] = new_url
```

## gw.alicdn.com images (special handling)

Some `gw.alicdn.com` URLs are rejected by APIs (403/400). Workaround:
download to local → base64 encode → send as data URI:

```python
import base64, requests
r = requests.get(url, timeout=30)
if r.status_code == 200:
    img_input = f"data:image/jpeg;base64,{base64.b64encode(r.content).decode()}"
    # use img_input in reference_images instead of URL
```

## Webp format images

Some alicdn images are `.webp` which may 404 when accessed as `.jpg`.
Check the actual extension in the URL and use it as-is, or skip if 404.

## Share URLs across variant rows

Main image and sub images are shared across all variant rows of the same
product. After processing row N's images, copy results to rows N+1..end of
that product group:

```python
# Product 1 = rows 2-30, Product 2 = 31-50, Product 3 = 51-95
products = [(2,30), (31,50), (51,95)]
for start, end in products:
    for col in [17] + list(range(18, 26)):  # main + sub1-8
        src_url = ws.cell(start, col).value
        if src_url and ("tos-cn" in src_url or "sd2oss" in src_url):
            for r in range(start+1, end+1):
                ws.cell(r, col).value = src_url
```

Variant images (col 28) are unique per row — process each individually.
