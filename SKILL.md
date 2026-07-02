---
name: tk-vn-product-sheet-skill
activation: /tk-vn-product-sheet-skill
description: >-
  Process TikTok cross-border e-commerce spreadsheets for Vietnam site:
  translate Chinese titles/variants to Vietnamese (de-branded, ≤80 chars),
  set brand→Generic N/A, stock→30, regenerate SKU, clear video links.
  Pre-screen product images via vision LLM → only send images containing
  brand/logo/watermark/text to Doubao Seedream 5.0 (2K) or GPT-Image-2
  for cleaning (remove brand/logo/watermark + translate text to Vietnamese).
  All URL→API→URL — no local file downloads needed. Triggers: tk越南站表格,
  tiktok产品表, 电商表格翻译越南语, 产品图去logo水印, 跨境电商数据清洗.
license: MIT
metadata:
  author: tk-vn-product-sheet-skill
  version: 4.0.0
  created: 2026-07-01
  last_reviewed: 2026-07-01
  review_interval_days: 90
  repository: https://github.com/23xxCh/tk-vn-product-sheet-skill
  os_family: cross-platform
  provenance:
    - source: https://github.com/mageia/skills-hub/skills/waninter-creative
      license: MIT
      adapted: true
    - source: agent-skill-creator (https://github.com/FrancyJGLisboa/agent-skill-creator)
      license: MIT
---

# /tk-vn-product-sheet-skill

Process Chinese-source TikTok Shop product spreadsheets into Vietnam-site-ready
listings. **Full URL→API→URL pipeline** — no local image downloads needed,
no image hosting required.

**For AI agents** — this skill tells you exactly how to process the spreadsheet
step by step, with curl commands ready to copy-paste.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/<user>/tk-vn-product-sheet-skill.git

# 2. Set API keys
export ARK_API_KEY="your_doubao_key_here"
export HFSY_API_KEY="your_hfsyapi_key_here"

# 3. Prepare (deterministic: brand/stock/SKU/video)
python scripts/run_pipeline.py prepare "0630-tk.xlsx" work.json

# 4. Translate titles/variants (agent fills work.json translations)

# 5. Vision pre-screen → image gen → write back (see workflow below)

# 6. Finalize
python scripts/run_pipeline.py finalize "0630-tk.xlsx" work.json "0630-tk.xlsx"
```

---

## Architecture

```
xlsx (94 rows, 45 cols)
  │
  ├─ Step 1: prepare      → 品牌/库存/SKU/视频 deterministic + dedup image inventory
  ├─ Step 2: translate    → 标题/变种 → Vietnamese (de-brand)
  ├─ Step 3: vision audit  → classify each image: keep/regen/delete (by URL, no download)
  ├─ Step 4: image gen     → nano-banana-2(4K) → Doubao(2K) → GPT-Image-2(1K) fallback chain
  ├─ Step 5-6: extract wt/dims + share URLs across variant rows
  ├─ Step 7-8: align 35-col template + finalize (backup .bak)
  └─ Step 9: empty value check
```

---

## API Keys (required)

Create an `.env` file in the skill directory (or export as env vars):

```bash
# Primary + Fallback2: nano-banana-2 (4K) & GPT-Image-2 (1K) — both via hfsyapi
HFSY_API_KEY="your_hfsyapi_key"

# Fallback1: Doubao Seedream 5.0 (2K, 火山引擎)
ARK_API_KEY="your_ark_api_key"

# Vision audit: Agnes 2.0 flash (classifies images by URL)
AGNES_API_KEY="your_agnes_api_key"
```

**Vision audit model priority:**
1. **minimax-m3** (Volcengine coding endpoint) — better recall on brand/logo/watermark
2. **agnes-2.0-flash** — fallback

**Image gen model priority (fallback chain):**
1. **gpt-image-2 /edits** (hfsyapi) — edit mode, best product preservation
2. **nano-banana-2** (hfsyapi) — 4K, up to 7 reference images
3. **Doubao Seedream 5.0** (Ark) — 2K fallback
4. **GPT-Image-2 /generations** (hfsyapi) — 1K fallback

> ⚠️ **去水印能力限制**: 所有模型都**没有真正的像素级 mask inpaint**。edits 模式
> 对原图保留度最好,但去水印/logo 仍是尽力而为(复杂背景上的水印可能残留)。
> VLM 能"看到"水印但给不出精确坐标,所以无法做精准遮罩擦除。

> **Open source note**: API keys are user-specific. The `.env` file is
> `.gitignore`d. Users must provide their own keys for the APIs they choose.

---

## Core Workflow

### Step 1 — Prepare (deterministic transforms)

```bash
python scripts/run_pipeline.py prepare "<xlsx_path>" work.json
```

Reads the xlsx, computes SKUs, normalizes URLs, deduplicates images,
outputs `work.json`. Does NOT modify the xlsx.

### Step 2 — Fill translations

Edit `work.json` manually or via script. For each row, set:

```json
{
  "row_index": 2,
  "translate": {
    "B": "Đệm nâng cao hộp tựa tay ô tô, bảo vệ tựa tay, da dày cao cấp, đa năng",
    "G": "Phân loại màu",
    "H": "Đệm nâng cao - đa năng + túi đựng"
  }
}
```

Rules (see `references/vietnamese-style.md` for full formula, category-word
table, and IP-infringement red-lines):
- **Title (B)** — 黄金公式: `[品类名词] + [核心卖点] + [适用/规格] + [通用词]`
  - 品类名词开头（越南人名词先搜），≤80 字符
  - 意译不直译，用越南本地实搜词（不是字典直译）
  - 删除 `原装`/`原厂`/`正品`/`专柜`/`官方`
  - 品牌词改「适用于」句式: `[品类] phù hợp với [品牌] [型号]`
  - 越南语音调符号必须正确（`ô tô` 不是 `o to`）
- **Variant names (G/I/K)**: `颜色分类→Phân loại màu`, `商品规格→Quy cách sản phẩm`
- **Variant values (H/J/L)**: de-brand + translate, 精简营销废话

**IP 红线**（TikTok VN 会下架/封店）: 品牌名当商品主体、`正品/高仿/1:1/原单`、
未授权 logo、绝对化用语（`最好/第一`）、联系方式外链。全部见 vietnamese-style.md。

### Step 3 — Vision audit + classification (REQUIRED, don't skip)

**Audit EVERY unique image URL with a vision LLM before processing.** This is
critical — missing a brand/logo/watermark = IP infringement risk.

```bash
# Audit each image via Agnes 2.0 flash (vision LLM, reads URL directly)
curl -X POST "https://apihub.agnes-ai.com/v1/chat/completions" \
  -H "Authorization: Bearer $AGNES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.0-flash",
    "messages": [
      {"role": "system", "content": "Audit product image. Output JSON: {\"has_brand_name\":bool,\"brand_names_found\":[],\"has_logo\":bool,\"has_watermark\":bool,\"has_chinese_text\":bool,\"is_promo_banner\":bool,\"needs_cleaning\":bool,\"cleaning_reason\":\"brand|logo|watermark|text|promo|none\",\"description\":\"\"}"},
      {"role": "user", "content": [
        {"type": "text", "text": "Audit this image for brand names, logos, watermarks, or Chinese text. Be thorough — do not miss small watermarks or corner logos."},
        {"type": "image_url", "image_url": {"url": "<IMAGE_URL>"}}
      ]}
    ],
    "max_tokens": 600
  }'
```

**Classification (from audit JSON) — depends on WHICH column the image is in:**

⚠️ **`delete` only applies to 产品描述(C列) images.** Main image (R), sub images
(S-Z), and variant image (AC) are NEVER deleted — they only get cleaned or kept.

| Column | Audit result | Decision | Action |
|--------|--------------|----------|--------|
| **C 描述** | `is_promo_banner: true` (客服/营销/优惠/售后图) | `delete` | Remove from description HTML |
| **C 描述** | has brand/logo/watermark/text | `regen` | Clean via image gen API |
| **R / S-Z / AC** | has brand/logo/watermark/text | `regen` | Clean via image gen API |
| **R / S-Z / AC** | `is_promo_banner: true` | `regen` or `keep` | **NEVER delete** — clean if it has brand/text, else keep |
| any | all false | `keep` | Original is fine, no processing |

**Real examples found in audit:**
- (C描述列) 客服/店铺声明/优惠券 banner → **delete** (only in description)
- `NIU` motorcycle logo on variant image (AC) → regen (remove logo, keep image)
- "舒适出行/记忆海绵增高垫" Chinese text → regen (translate)
- "LIMITED EDITION" English text, no brand → keep (English is fine)

> **关键规则**: 主图/附图/变种图**绝不删除**,只做去品牌/logo/水印+翻译。
> 只有**产品描述(C列)**里与产品无关的图(客服图/营销图/优惠信息/售后信息)才删除。

> **Lesson learned**: Always audit. The vision LLM catches small corner logos,
> background watermarks, brand names that are easy to miss. See
> `references/image-rules.md` for full audit protocol.

### Step 4 — Batch image generation

Process only `brand`/`text` images. Send multiple requests in parallel.

**Primary — nano-banana-2** (up to 4K, supports up to 7 reference images):

```bash
curl -X POST "https://www.hfsyapi.cn/v1beta/models/nano-banana-2:generateContent" \
  -H "Authorization: Bearer $HFSY_API_KEY" \
  -H "Content-Type: application/json" \
  -H "User-Agent: curl/7.68.0" \
  -d '{
    "contents": [{
      "parts": [
        {"text": "Remove brand names, logos and watermarks from the image, and translate all text to Vietnamese."},
        {"fileData": {"mimeType": "image/jpeg", "fileUri": "<IMAGE_URL>"}}
      ]
    }],
    "generationConfig": {"imageConfig": {"imageSize": "4K", "aspectRatio": "1:1"}}
  }'
```

**Response:** URL in `candidates[0].content.parts[].fileData.fileUri`

Or use the wrapper: `python scripts/nano_gen.py clean --image "<url>" --size 4K`

**Fallback 1 — Doubao Seedream 5.0** (2K):

```bash
curl -X POST "https://ark.cn-beijing.volces.com/api/v3/images/generations" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seedream-5-0-260128",
    "prompt": "Remove brand names, logos and watermarks from the image, and translate all text to Vietnamese.",
    "image": "<IMAGE_URL>",
    "sequential_image_generation": "disabled",
    "response_format": "url", "size": "2K", "watermark": false
  }'
```

**Fallback 2 — GPT-Image-2 via hfsyapi** (1K):

```bash
curl -X POST "https://www.hfsyapi.cn/v1/images/generations" \
  -H "Authorization: Bearer $HFSY_API_KEY" \
  -H "Content-Type: application/json" \
  -H "User-Agent: curl/7.68.0" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "Remove brand names, logos and watermarks from the image, and translate all text to Vietnamese.",
    "reference_images": ["<IMAGE_URL>"], "size": "1024x1024", "n": 1, "response_format": "url"
  }'
```

**⚠️ ALL returned URLs are signed links that expire in ~24 hours.** Upload to
TikTok Shop promptly (TikTok caches to its own CDN, so expiry doesn't matter
once uploaded). If you process a sheet but don't list within 24h, re-run the
image gen from the original alicdn URLs (preserved in the sheet source column).

**Speed tips:**
- **Deduplicate first**: 94 rows × 12 images = 1128 → typically only **120 unique images**
- **Parallelize**: Run 5-10 concurrent requests
- **For gw.alicdn images**: Some CDNs block API fetch. Download → base64 → send as data URI. See `references/recipes.md`.

### Step 5 — Extract weight/dimensions (from text-containing images)

When an image is classified as `text`, use the vision LLM to also extract
any weight or dimension information:

```bash
curl -X POST "https://apihub.agnes-ai.com/v1/chat/completions" \
  -H "Authorization: Bearer $AGNES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.0-flash",
    "messages": [
      {"role": "system", "content": "Extract product weight and dimensions from the image. If weight is shown in g/lb/jin, convert to kg. If dimensions are shown, extract as LxWxH in cm. Output JSON."},
      {"role": "user", "content": [
        {"type": "text", "text": "Read all text in this product image. Extract weight (convert to kg) and dimensions (cm)."},
        {"type": "image_url", "image_url": {"url": "<IMAGE_URL>"}}
      ]}
    ],
    "max_tokens": 512
  }'
```

→ Write to `row.weight_kg`, `row.l`, `row.w`, `row.h` in work.json

### Step 6 — Apply shared URLs

Main image and sub image results are shared across all variant rows of the
same product. After processing the first row's images, copy the results
to all other rows of that product.

### Step 7 — Align to output template (35 columns)

Input xlsx has 45 columns (A-AS). TikTok Vietnam output template requires
exactly **35 columns**. After finalize, restructure:

- **Rename**: Column O "价格(站点币种)" → "本地展示价(站点币种)"
- **Drop**: columns 37-45 (备注/店铺名/sku ID/产品id/全球id/店铺币种/时间)

See `references/output-template.md` for the exact 35-column structure and
template headers (including `*` and `（必填）` markers).

### Step 8 — Finalize

```bash
python scripts/run_pipeline.py finalize "<xlsx>" work.json "<xlsx>"
```

Writes everything back. Backs up original first.

### Step 9 — Empty value check (REQUIRED)

Verify all `*` required fields are filled (TikTok rejects empty required fields):

```bash
python scripts/check_sheet.py "<xlsx>" <check_name>
```

**Required**: 分类id, 产品标题, 产品描述, 本地展示价, 库存, 产品主图,
重量(kg), 长(cm), 宽(cm), 高(cm), 仓库名称.

**Fill strategy for empty weight/dimensions:**
1. Extract from image text (vision LLM)
2. Extract from variant values (e.g. "3.0cm [dài 5m]" → W=3, L=500)
3. Reasonable estimate by product type (see `references/output-template.md`)

> Never leave required fields empty. See `references/output-template.md` for
> the full fill strategy and verification protocol.

---

## Field Map

| Col | Field | Description | Treatment |
|-----|-------|-------------|-----------|
| B | 产品标题 | Product title | Agent: Chinese→Vietnamese, ≤80, de-brand |
| C | Tiktok产品描述 | HTML `<img src=…>` description | **Delete** unrelated imgs (客服/营销/优惠/售后), clean+swap product imgs |
| D | 品牌 | Brand name | Deterministic: `Generic N/A` |
| F | sku | SKU number | Deterministic: `YYYYMMDD + 5-digit` |
| G | 变种属性名称一 | Variant attr name 1 | Agent: Vietnamese |
| H | 变种属性值一 | Variant attr value 1 | Agent: de-brand + Vietnamese |
| I/J | 变种属性名称/值二 | Variant attr 2 | Same as G/H |
| K/L | 变种属性名称/值三 | Variant attr 3 | Same as G/H |
| Q | 库存 | Stock quantity | Deterministic: `30` |
| R | 主图(url)地址 | Main product image | Vision audit → clean if brand/text → share to all rows. **NEVER delete** |
| S-Z | 附图一~八 | Sub images 1-8 | Same as R: clean if brand/text, else keep. **NEVER delete** |
| AA | 视频连接 | Video link | Deterministic: clear |
| AC | 变种主题1图片 | Variant theme image | Vision audit → clean if brand/text (each row different). **NEVER delete** |
| AD | 重量(kg) | Weight in kg | Vision extract from image text |
| AE/AF/AG | 长/宽/高 | Dimensions L/W/H in cm | Vision extract from image text |

> **删除规则只对 C列(产品描述)生效**。主图R/附图S-Z/变种图AC 绝不删除，
> 只做去品牌/logo/水印+翻译越南语；干净图保留原样。

---

## Recipes

See `references/recipes.md` for complete Python batch processing code:
- Parallel vision audit (10 concurrent) + image gen (5 concurrent)
- Doubao→hfsyapi fallback logic
- gw.alicdn base64 workaround
- Sharing URLs across variant rows

---

## Batch auto-process (one command, fastest)

```bash
# Set keys
export ARK_API_KEY="..."
export HFSY_API_KEY="..."
export AGNES_API_KEY="..."

# One command: prepare → vision audit → parallel gen → finalize
python scripts/batch_process.py "0630-tk.xlsx"
```

This script does everything in one shot:
1. `prepare` — deterministic transforms (<1s)
2. Vision audit all unique images (12× parallel)
3. Batch image gen for brand/text only (8× parallel, nano→Doubao→GPT fallback)
4. Share URLs + finalize

**No bash timeouts, no manual restart, no sequential waiting.**

## Folder watch mode (drop file → auto-process, no prompting)

For "just drop the file in a folder and it processes itself" workflow:

```bash
python scripts/watch.py            # starts the watcher (runs until Ctrl+C)
```

- Watches `./tk_input/` folder (polls every 5s, zero dependencies)
- Drop any `.xlsx` into `tk_input/` → auto-runs full pipeline
- Result appears in `./tk_output/` (as `<name>_processed_<timestamp>.xlsx`)
- Original moved to `./tk_done/` (won't be reprocessed)
- Waits for file write to finish (size-stable check), ignores Excel `~$` lock files

> ⚠️ **Note**: An AI agent has no background daemon — it can't watch folders on
> its own. `watch.py` is a standalone Python process the user starts once; it
> then runs unattended. The agent only runs when you send a message. For
> "auto-process on drop" you MUST run `watch.py` (a real long-running process),
> not rely on the agent noticing files.

Options: `--input`/`--output`/`--done` folders, `--interval` seconds,
`--gen-size 4K`, `--audit-workers 12 --gen-workers 8`.

---

## Why This Is Fast

| Optimization | Speedup | How |
|-------------|--------|-----|
| **Vision pre-screen** | 10-20× | Classify by URL (no download). Only 20-40% need generation |
| **Deduplication** | 10× | 94 rows → ~120 unique images (not 1128) |
| **Parallel API calls** | 5-10× | Concurrent vision+gen instead of sequential |
| **Direct URL input** | 3× | APIs accept image URLs directly (no base64) |
| **Single script** | 2× | No bash timeout, no manual restart |

**Benchmark (94-row, ~120 unique images):**
- Sequential, no pre-screen: ~60 min (120× gen) ❌
- Sequential + pre-screen: ~15-20 min (120× vision + ~35× gen)
- **Parallel + pre-screen (batch_process.py)**: **~3-5 min** ✅

---

## URL Expiry

Both Doubao (TOS) and hfsyapi (OSS) return **signed URLs** with ~24hr validity.
This is sufficient for:
1. Paste URLs into spreadsheet
2. Upload to TikTok Shop platform (TikTok caches to its own CDN)
3. Once cached, expiry doesn't matter

If re-upload is needed later, run the pipeline again from Step 3 (the original
image URLs remain unchanged).

---

## Installation (for open source users)

```bash
git clone https://github.com/<user>/tk-vn-product-sheet-skill.git
cd tk-vn-product-sheet-skill
pip install openpyxl requests

# Set up API keys
cp .env.example .env
# Edit .env with your API keys
```

Requirements:
- Python 3.8+
- `openpyxl` (xlsx reading/writing)
- `requests` (API calls)
- API keys for Doubao Seedream / hfsyapi / Agnes vision

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/run_pipeline.py` | `prepare` (xlsx→work.json) + `finalize` (work.json→xlsx) |
| `scripts/sheet_io.py` | xlsx dump/apply utilities |
| `scripts/nano_gen.py` | nano-banana-2 image gen wrapper (4K) |
| `scripts/edit_gen.py` | **gpt-image-2 /edits wrapper (primary, best preservation)** |
| `scripts/agnes_gen.py` | hfsyapi GPT-Image-2 generations wrapper (fallback) |
| `scripts/agnes_read.py` | Vision audit via minimax-m3 → agnes-2.0-flash fallback |
| `scripts/batch_process.py` | Parallel batch: audit + gen + write, one command |
| `scripts/watch.py` | Folder watcher: drop xlsx → auto-process (unattended) |
| `scripts/fetch_image.py` | Download image URL to file (for local inspection) |
| `scripts/check_sheet.py` | Validate processed xlsx |
| `scripts/check_pipeline.py` | Module availability check |

---

## References

- `references/field-mapping.md` — Full column map, per-field rules, 35-col output template
- `references/image-rules.md` — Vision audit protocol + image classification + API details
- `references/output-template.md` — 35-column template structure + empty value check + fill strategy
- `references/recipes.md` — Python batch processing code (parallel audit + gen, fallbacks)
- `references/vietnamese-style.md` — Vietnamese title/variant style + IP-safe rules

---

## License

MIT — use freely, modify, share.
