# Crawl Report — Bổ sung dữ liệu thiếu cho merchants

**Date:** 2026-07-20 | **Status:** HOÀN TẤT 1.625/1.625 quán

## Kết quả cuối cùng
| Chỉ số | Kết quả |
|---|---|
| Tổng quán crawl | 1.625 / 1.625 (100%) |
| Menu đầy đủ | 1.614 (99.4%) — 102.886 món, TB 63 món/quán |
| Rating thật | 1.624 (99%) |
| Reviews thật (≥1) | 652 quán (40%) — 4.370 review |
| Hero candidates (≥5 rev & ≥10 món) | 383 quán |
| Menu rỗng không cứu được | ~9 (quán đã đóng/gỡ, rating=0) |
| Dung lượng | 523 MB (đã gitignore) |

**Vận hành:** crawl bị môi trường dừng (killed) nhiều lần nhưng resume-safe (bỏ qua file đã có) nên chạy lại tiếp tục; hoàn tất sau ~4 lần phóng. Đã sửa 1 crash (`reply=None`) + bọc try/except per-merchant. Data crawl (523MB) + merchants_unique.jsonl đã thêm vào `.gitignore`.

---
_(chi tiết phương pháp bên dưới)_

## Kết luận: KHÔNG cần Firecrawl — crawl được bằng công cụ local miễn phí

### Rào cản gặp phải
- API `gappapi.deliverynow.vn` (ShopeeFood) chặn bằng chữ ký chống bot: header `x-sap-ri` + các header **tên ngẫu nhiên đổi mỗi phiên** (do JS obfuscated Shopee sinh runtime). `curl`/`context.request` trần → HTTP 403 `error 90309999`. Không giả mạo được từ Python.
- Replay in-page (`fetch`/`XHR` qua page.evaluate) → CORS chặn (status 0 / Failed to fetch).

### Giải pháp chạy được (đã kiểm chứng pilot 5/5 OK)
| Dữ liệu | Nguồn | Cách lấy |
|---|---|---|
| Menu đầy đủ (món, giá, giá giảm, ảnh nhiều res, lượt thích) | ShopeeFood `get_delivery_dishes` | Playwright (channel=chrome) **bắt response thụ động** khi nav vào trang |
| Rating thật, review count, restaurant_id, brand_id, sđt, is_quality_merchant | ShopeeFood `get_detail` | Playwright bắt response thụ động |
| Reviews (text + điểm/10) + rating tổng Foody | Trang **Foody** (cùng slug) render sẵn HTML | **urllib + parse regex** — không cần browser, không cần API ký |

**Mấu chốt liên kết:** Foody dùng cùng slug với ShopeeFood (`foody.vn/{location}/{slug}`), slug có sẵn trong `source_url`. → reviews lấy được cho toàn bộ quán bằng HTTP thường.

## Dữ liệu & quy mô
- Dedupe: 3.277 records → **1.681 quán unique** (gộp bản network+DOM, ưu tiên ID số, loại DOM lỗi tên) → `data/merchants_unique.jsonl`.
- Crawl: **1.625 quán có merchant_id số** (gọi API được). 56 quán slug-only bỏ qua.
- Output: `data/crawled/{merchant_id}.json` (~30-40KB/quán), resume-capable (bỏ qua file đã có).
- Pilot: rating 4.8-4.9, menu 14-171 món, 10 review/quán, đủ khen/chê (phục vụ sentiment).

## Data quality notes
- `shopeefood_total_review` bị chặn ở 1000 ("999+") → dùng `foody_review_count` cho số chính xác khi thấp.
- Rating gốc trong catalog cũ (`merchant_rating`=1000) thực ra là review count map nhầm → nay có `avg` thật.
- Reviews Foody: ~10-12 review đầu/quán (nhúng HTML). Trang sâu hơn cần AJAX ký (bỏ, đủ dùng cho demo).

## Files
- `scripts/crawl/dedupe_catalog.py` — dedupe (không mạng)
- `scripts/crawl/foody_review_parser.py` — parse review từ HTML Foody (thuần hàm)
- `scripts/crawl/crawl_merchants.py` — crawler chính (Playwright + Foody), `--limit/--start/--delay`
- `plans/reports/crawl-progress.log` — log tiến độ live (theo dõi qua `ls data/crawled | wc -l`)

## Vẫn còn thiếu (KHÔNG crawl được → synthetic ở bước sau, đúng PRD v2)
- Complaints, Delivery feedback (tài xế), Operational metrics nội bộ → LLM synthetic.
- Reviews sâu (>12/quán) → nếu cần thêm, dùng nhiều review hiện có + synthetic.

## Unresolved questions
- Có ẩn danh tên quán khi pitch công khai không?
- Ước tính ~15-20 quán/9 thành phố có thể không tồn tại trên Foody (chỉ ShopeeFood) → review rỗng, chấp nhận.
- Full crawl ~2-2.5h; kiểm tra lại `crawl_errors` sau khi xong để retry quán lỗi nếu nhiều.
