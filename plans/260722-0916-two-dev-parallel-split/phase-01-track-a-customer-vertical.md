# Phase 1 — Track A: Customer Discovery Vertical (Dev A)

> Owner: Dev A. Branch từ `phase0-freeze`. Chạy SONG SONG với Phase 2. Full-stack (BE + FE).
> Scope UC: UC-04 (search), UC-05 (preference/context reasoning).

## File ownership (glob — chỉ Dev A sửa)
```
backend/repositories/{merchant,user_profile,session,preference_event,interaction_event}_repository.py
backend/services/{merchant_search,customer_context,preference,session,weather,geocode,map}_service.py
backend/providers/{cache,weather,geocode,routing}/*
backend/tools/{merchant_search,nearby_merchant,user_profile,profile_delta,weather,geocode}_tool.py
backend/agents/customer/*   (+ agents/customer/config/*.yaml)
backend/flows/customer_flow.py
backend/routes/{merchant_search,user,event,map,customer_agent}_routes.py
frontend/src/customer/*
```

## Deliverables (map task doc)
### Data/domain
- [ ] C-01 catalog repos: merchant/menu/review access (`merchant_repository.py`)
- [ ] C-03 user/session/event repos (durable memory + audit)
- [ ] C-04 search/ranking service → structured ranked candidates (§11.2)

### Cache (impl, interface + memory adapter đã ship Phase 0)
- [ ] D-02 **Redis adapter only** (memory adapter đã ở Phase 0 — [H4]) (`providers/cache/redis_adapter.py`)
- [ ] D-03 session context service (snapshot load/save/restore §8)
- [ ] D-04 TTL + invalidation rules (§8.2)
- [ ] **[H7] front-load** `nearby_merchant_search` + memory adapter (đã làm ở Phase 0.5) để Dev B (Competitor) không chờ

### Preferences (Feature E)
- [ ] E-01 ingest interaction events (§11.7) `POST /users/{id}/events`
- [ ] E-02 rule-based profile delta candidate generation (§7.1)
- [ ] E-03 confirm/reject/delete deltas (§11.6, audited)
- [ ] E-04 Preference Center UI (§7.2) — confirmed/session/pending + source display

### Tools/providers
- [ ] F-02(customer) wrap: merchant_search, nearby_merchant, user_profile, profile_delta, weather, geocode tools
- [ ] F-03 Open-Meteo + Nominatim adapters (cached §16 fallback)
- [ ] F-04 Haversine + GeoJSON map service (§11.8)
- [ ] F-05 optional OSRM adapter (labeled fallback)

### Customer Agent (Feature G)
- [ ] G-01 customer agents/tasks config (`agents/customer/config/*.yaml`)
- [ ] G-02 Customer Discovery Crew: coordinator + search + preference + explanation (§5.2)
- [ ] G-03 chat API + SSE (`POST /agent/customer/chat` §11.4)
- [ ] G-04 scenario tests UC-04, UC-05

### Map/Context UI (Feature K)
- [ ] K-01 Leafmap render backend GeoJSON (user/merchant/radius)
- [ ] K-02 result cards ↔ map selection sync, "Vì sao gợi ý?"
- [ ] K-03 weather + preference controls UI

### Frontend (customer)
- [ ] Chat page + SSE stream render
- [ ] Search results + map (leafmap iframe theo §10)
- [ ] Preference Center (§7.2) + interaction events (§7.2 taxonomy)
- [ ] Geolocation permission flow (§10)

## Depends on / seam contracts (từ Phase 0, KHÔNG sửa)
- CachePort + memory adapter (Phase 0), models/api.py, tool registry, event schema, API §11.
- **[C1]** Customer Explanation agent consume `get_merchant_profile` (shared read-only tool đã frozen ở Phase 0) — KHÔNG chờ Track B; grant qua allow-list artifact chung.
- Emit CrewAI event chuẩn → verify bằng contract test Phase 0 (không đợi merge) → listener Dev B persist.

## Success criteria
- Customer search chạy với dataset nhỏ hiện có (§18)
- Weather/location supply hoặc override được
- Preference suggestion cần confirm mới persist; click KHÔNG đổi global profile
- Leafmap render merchant GeoJSON, distance card == API
- UC-04, UC-05 pass end-to-end với fixture nhỏ

## Security (§17)
- Location session-scoped trừ khi confirm; Nominatim có User-Agent + cache; API key ở env.

## Interface Dev B sẽ consume (giữ ổn định)
- `nearby_merchant_search` tool schema (Competitor của B dùng) — freeze I/O, báo B trước nếu đổi.
