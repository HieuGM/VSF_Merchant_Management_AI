# Phase 0.5 — Walking Skeleton (UC-04 end-to-end, CHUNG)

> Owner: **bạn (owner) solo** → bàn giao (Validation S1). Sau Phase 0, TRƯỚC khi fork. Nguồn: Red-team C3/C1/H4/H7/H8.
> Slice này chính là **reference demo** để 2 dev đọc-hiểu contract khi handoff.
> Mục tiêu: build 1 vertical slice mỏng UC-04 (restaurant search) xuyên hết stack để **chứng minh** các seam Phase 0 ĐÚNG trước khi đóng băng + fork. Không đoán contract.

## Vì sao
Freeze CachePort/event schema/tool registry/migration khi CHƯA có consumer = premature (red-team C3). Slice UC-04 chạm đủ mọi seam: DB→repo→service→tool→registry→flow→event→route→cache→React. Chạy được nó = contract proven. Sau đó freeze mới an toàn.

## Deliverables (mỏng, chỉ đủ 1 luồng chạy)
- [ ] Migration + seed: `merchants`/`menu`/`reviews` + resettable additive seed (kéo L-03 lên đây) — chứng minh migration-chain + seed idempotent
- [ ] `merchant_repository` + `merchant_search_service` (1 query search cơ bản §11.2) — mỏng
- [ ] `merchant_search_tool` qua registry (chứng minh metadata + allow-list artifact §9.1)
- [ ] `nearby_merchant_search` tool (Haversine) — **front-load [H7]** vì Competitor của Dev B cần
- [ ] Shared read-only tools stub proven: `get_merchant_profile`, `get_trending_dishes` (Phase 0 seam #6) — trả fixture tối thiểu
- [ ] `customer_flow` tối thiểu gọi 1 agent + emit event chuẩn → **reference listener persist agent_events** (chứng minh event schema H8)
- [x] Route `GET /merchants/search` thật (thay stub 501) + cache candidate qua in-memory adapter (chứng minh CachePort H4) — **VERIFIED: endpoint returns 200, input validation secured, SQL injection protected**
- [ ] React: 1 trang search gọi API thật, render kết quả (chứng minh API client + shared UI)

## Success criteria (GATE trước khi fork)
- UC-04 chạy thật: gõ query → API → tool → DB → kết quả trên React
- 1 agent_run + agent_events ghi được, có trace_id (event schema proven)
- Cache candidate hit/miss chạy với in-memory adapter (không cần Redis)
- Registry allow-list chặn tool ngoài danh sách (proven)
- `alembic upgrade head` + reset seed chạy lặp được
- **Chỉ SAU khi pass hết → tag `phase0-freeze`, fork Track A/B.** Nếu 1 seam sai → sửa NGAY tại đây (chưa fork nên rẻ)

## Điều được "proven" và freeze sau slice này
CachePort shape · event record schema (agent_events fields) · tool registry metadata thực dùng · migration-chain pattern · API client ↔ contract · router-replace pattern (stub→thật). Đây là các thứ red-team cảnh báo "đoán sai".

## Next
Pass gate → Phase 1 (Dev A) + Phase 2 (Dev B) song song, adopt pattern đã proven (không đoán lại).
