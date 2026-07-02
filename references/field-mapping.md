# Field Mapping — `tiktok_chanpin_` sheet

Full column map (row 1 headers) and per-field treatment for the Vietnam pipeline.

| Col | Header | Direction | Rule |
|-----|--------|-----------|------|
| A | 分类id | keep | unchanged |
| B | 产品标题 | translate | → Vietnamese ≤80 chars; drop 原装/原厂; de-brand; IP-safe |
| C | Tiktok产品描述 | rewrite | 文字+图片混合: **文字**去品牌+译越南语; **图片**删无关(客服/营销/售后),保留产品图,产品图有字/品牌则生图清洗; 文字+图片重组 |
| D | 品牌 | set | **留空**（清空，不填任何值） |
| E | 产品属性 | keep | already Vietnamese JSON; leave as-is |
| F | sku | set | `YYYYMMDD` + 5-digit sequence (e.g. `2026070100001`) |
| G | 变种属性名称一 | translate | de-brand → Vietnamese (`颜色分类`→`Phân loại màu`) |
| H | 变种属性值一 | translate | de-brand → Vietnamese |
| I | 变种属性名称二 | translate | de-brand → Vietnamese |
| J | 变种属性值二 | translate | de-brand → Vietnamese |
| K | 变种属性名称三 | translate | de-brand → Vietnamese |
| L | 变种属性值三 | translate | de-brand → Vietnamese |
| M | 识别码类型 | keep | — |
| N | 识别码 | keep | — |
| O | 价格(站点币种) | **rename** | 标题改为 `本地展示价`，值保留（finalize自动做） |
| P | 本地展示价 | **drop** | 删除此空列（finalize自动做） |
| Q | 库存 | set | `30` |
| R | 主图(url)地址 | clean | normalize; regen if brand/logo/watermark/text |
| S–Z | 附图一~八 | clean | same as 主图 |
| AA | 视频连接 | clear | empty |
| AB | 尺码图 | keep | — |
| AC | 变种主题1图片 | clean | normalize; regen if needed |
| AD | 重量(kg) | extract/fill | from image text, unit-converted to kg; 无则填合理估值 |
| AE | 长 | extract/fill | from image text; 无则填合理估值 |
| AF | 宽 | extract/fill | from image text; 无则填合理估值 |
| AG | 高 | extract/fill | from image text; 无则填合理估值 |
| AH–AS | 仓库/货到付款/来源/备注/店铺/sku ID/产品id/全球id/店铺币种/时间 | **drop** | 删除多余列,只保留模板35列 |

## Output template (35 columns)

最终输出必须对齐 TikTok 模板 `template_tiktok.xlsx` 的 **35列** 结构：

```
1.分类id  2.产品标题  3.产品描述  4.品牌  5.产品属性  6.SKU
7-12.变种属性名称/值一二三  13.识别码类型  14.识别码
15.本地展示价(站点币种)  16.库存  17.产品主图  18-25.附图一~八
26.视频链接  27.尺码图  28.变种主题1图片
29.重量(kg)  30.长(cm)  31.宽(cm)  32.高(cm)  33.仓库名称
34.货到付款  35.来源URL
```

输入的45列(A-AS)中，列37-45(备注/店铺名/skuID/产品id/全球id/店铺币种/创建时间/更新时间/平台刊登时间)需删除。

## Image source columns

- `main` → R (主图)
- `sub` → S,T,U,V,W,X,Y,Z (附图一~八)
- `variant` → AC (变种主题1图片)
- `desc` → URLs parsed out of C's `<img>` tags

## Unit conversion (weight → kg)

| Source unit | Conversion |
|-------------|-----------|
| g (gram) | ÷1000 |
| kg | as-is |
| lb (pound) | ×0.4536 |
| oz (ounce) | ×0.0283 |
| jin (斤) | ×0.5 |

Result rounded to 3 decimals. If no weight found, leave AD empty.

## Dimensions (AE/AF/AG)

Default unit cm. Extract the numeric value only. If only one combined
"长x宽x高" string is shown, split into l/w/h. If none, leave empty.
