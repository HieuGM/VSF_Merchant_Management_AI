# Phase 3 — Integration & Evaluation

> Owner: 2 dev pair. Sau khi Phase 1 + Phase 2 xong. Ghép 2 vertical, xử phần cross-domain, demo hardening.

## Vì sao để cuối
Feature I (coordination) + L (evaluation) đụng CẢ 2 domain → không chia độc lập được. Làm chung, ít file, ngắn.

## Deliverables (map task doc)
### Multi-agent coordination (Feature I)
- [ ] I-01 coordinator delegation 1-hop (customer coordinator do A, merchant coordinator do B — đã có; đây là verify cross-crew)
- [ ] I-02 timeout + partial-result policy (§16 specialist failure → coordinator trả partial + warning)
- [ ] I-03 validate tool + delegation allow-list (security/contract test §5.4) — kiểm cả 2 registry allow-list

### Evaluation & demo hardening (Feature L)
- [ ] L-01 fixed evaluation cases (customer + merchant dataset versioned)
- [ ] L-02 đo tool/evidence correctness → report; latency/token log
- [ ] L-03 resettable demo seed (rerun được §18)
- [ ] L-04 end-to-end acceptance — 10 scenario §15, ký checklist

## Merge protocol
> **[C3/Failure — KHÔNG big-bang]** Đây KHÔNG phải lần đầu 2 track gặp nhau. Suốt Phase 1/2 đã **rebase `develop` ≥2 lần/tuần + boot smoke test** + có checkpoint tích hợp giữa kỳ. Phase 3 chỉ là ghép cuối, rủi ro nhỏ.
1. Rebase cuối lên `develop` (đã đồng bộ liên tục → conflict tối thiểu). Migration: cả 2 revision đã serialize qua migration-chain owner → **không 2-head**; nếu lỡ có, chạy `alembic merge heads` (đã pre-plan).
2. Chạy full test 2 track; fix regression.
3. Wire cross-domain: listener B nhận event flow A **đã verify từ Phase 0 contract test** — ở đây chỉ smoke lại.
4. FE: gộp 2 app dưới cùng shell (routing `/customer/*` vs `/merchant/*`).

## Contingency (1 track trễ)
- Mỗi vertical sau feature-flag → demo được độc lập (merchant-only hoặc customer-only) nếu track kia chưa xong.
- Branch-revert runbook: gỡ 1 vertical khỏi `develop` không kéo sập cái kia (nhờ file-ownership tách + flag).

## Success criteria (Definition of Done §18)
- Backend start với PostgreSQL + Redis
- Customer search chạy dataset nhỏ; weather/location override được
- Preference cần confirm; confirmed preference xem/sửa/audit được
- Leafmap render merchant GeoJSON
- Merchant fixture theo full profile contract; diagnosis/recommendation/comparison có evidence
- CrewAI delegation qua coordinator; trace ID + tool/task event inspect được
- 5 use case pass end-to-end; không flow nào cần full crawled dataset
- Demo reset + rerun được

## Checklist gate cuối
- [ ] 10 end-to-end scenario (§15) pass
- [ ] overall_score không lộ ở bất kỳ surface nào (C2)
- [ ] mọi agent response có trace_id
- [ ] allow-list test pass (không agent nào có tool ngoài registry)
