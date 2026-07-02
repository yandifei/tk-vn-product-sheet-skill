# Eval — tk-vn-product-sheet-skill

Binary checks + golden cases. Golden cases are `pending-first-green` (input-only)
until a first passing rollout baseline is promoted via `--promote`.

```json
{
  "skill": "tk-vn-product-sheet-skill",
  "criteria": [
    {
      "id": "brand_set",
      "text": "Every data row's column D (品牌) is empty",
      "type": "command",
      "cmd": "python scripts/check_sheet.py {output} brand_set"
    },
    {
      "id": "stock_set",
      "text": "Every data row's column Q == 30",
      "type": "command",
      "cmd": "python scripts/check_sheet.py {output} stock_set"
    },
    {
      "id": "video_cleared",
      "text": "Every data row's column AA (video link) is empty",
      "type": "command",
      "cmd": "python scripts/check_sheet.py {output} video_cleared"
    },
    {
      "id": "sku_format",
      "text": "Every SKU is 13 digits (8 date + 5 seq) and strictly increasing",
      "type": "command",
      "cmd": "python scripts/check_sheet.py {output} sku_format"
    },
    {
      "id": "image_urls_https",
      "text": "Every non-empty image URL in R,S-Z,AC and every <img src> in C starts with https://",
      "type": "command",
      "cmd": "python scripts/check_sheet.py {output} image_urls_https"
    },
    {
      "id": "title_vietnamese_and_short",
      "text": "Column B is Vietnamese, <=80 chars, and contains neither 原装 nor 原厂 (llm-judge)",
      "type": "llm-judge"
    },
    {
      "id": "no_promo_imgs_in_desc",
      "text": "Description HTML contains no promo/after-sales/banner image URLs, only product/spec images (llm-judge)",
      "type": "llm-judge"
    }
  ],
  "golden": [
    {
      "id": "variant_row_brandfree",
      "input": "case1_input.txt",
      "expected_status": "pending-first-green"
    },
    {
      "id": "title_with_brand_word",
      "input": "case2_input.txt",
      "expected_status": "pending-first-green"
    },
    {
      "id": "image_with_weight_text",
      "input": "case3_input.txt",
      "expected_status": "pending-first-green"
    },
    {
      "id": "promo_image_in_desc",
      "input": "case4_input.txt",
      "expected_status": "pending-first-green"
    },
    {
      "id": "clean_product_photo",
      "input": "case5_input.txt",
      "expected_status": "pending-first-green"
    }
  ]
}
```

## Scoring notes

`--output` scoring runs each `command` criterion's `cmd` via the runner's
`shell=True` subprocess. On **Windows**, paths containing spaces break because
cmd.exe tokenizes on spaces inside the shlex-quoted argument. To score on
Windows, copy the produced xlsx to a space-free path first
(`cp out.xlsx /tmp/out.xlsx`) then `python scripts/run_evals.py --output /tmp/out.xlsx`.
On posix, paths with spaces work normally. All five command checks pass against
a correct finalize output (verified); the two `llm-judge` checks are graded
manually or via `/autoresearch-universal`.

## Golden case descriptions

- **case1** — single variant row, brand-free title `汽车扶手箱垫中央增高垫...`, brand empty, stock 200, sku `5072154792617`, video link present, main + 8 sub + variant images, weight 0. Expect D→empty, Q→30, AA empty, F→`YYYYMMDD#####`, B→Vietnamese ≤80 no 原装/原厂, all image URLs https.
- **case2** — title `苹果原装手机壳iPhone保护套`. Expect rewritten as compatible-with form, ≤80 chars, no 原装.
- **case3** — image states 重量: 500g, dimensions 20x15x10cm. Expect AD→0.5, AE/AF/AG→20/15/10.
- **case4** — description contains a 满减优惠券 banner among product images. Expect banner URL removed from C.
- **case5** — main image is a plain product photo, no brand/text/watermark. Expect decision keep, original URL unchanged (no API call).
