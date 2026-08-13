# Research Report: H3 vs Routing — Fix "khoảng cách đường chim bay"

**Date:** 2026-07-30
**Scope:** Đánh giá H3 (Uber) có hợp lý hơn Haversine cho distance; đề xuất kiến trúc khoảng cách thực tế cho merchant search.

---

## Executive Summary (TL;DR — brutal honest)

**Giả thuyết user: "H3 sẽ hợp lý hơn đường chim bay" → KHÔNG ĐÚNG theo nghĩa user nghĩ.**

H3 là **spatial index lục giác**, **KHÔNG phải routing engine**. Nó tính *grid-distance* (số "hops" giữa cell), vẫn là khoảng cách hình học thuần, **không biết đường/phố/sông/highway tồn tại**. Đổi Haversine → H3 = "đường chim bay mặc áo lục giác" — **không giải quyết pain "khoảng cách không thực tế"**. [H3 traversal docs](https://h3geo.org/docs/api/traversal/), [r/gis drive-time thread](https://www.reddit.com/r/gis/comments/1sumk4w/)

Để có **khoảng cách/thời gian thực tế** (đường bộ, có tính giao thông) → cần **routing engine** (OSRM / GraphHopper / Valhalla self-host) hoặc **Matrix API** (OpenRouteService / Google / Mapbox). Đây mới là lời giải đúng cho yêu cầu user.

**Khuyến nghị (3 pha, YAGNI):**
1. **PHA 1 (giải pain thật):** Routing matrix trên top-K candidate (ORS free hoặc OSRM self-host VN) → distance_km + driving_min thực tế + ETA. Cache theo cell.
2. **PHA 2 (efficiency, chỉ khi scale):** PostGIS `ST_DWithin` + GIST index thay scan O(n) Python. Đơn giản, chuẩn Postgres, hơn H3 nhiều ở quy mô này.
3. **PHA 3 (chỉ khi cần analytics đa vùng):** Lúc đó H3 mới tỏa (surge/region bucketing như Uber).

**Kết luận 1 câu:** Dùng routing cho "thực tế", dùng PostGIS cho "nhanh", **H3 chỉ khi muốn mở rộng quy mô/phân tích** — không phải để thay Haversine.

---

## Current State (codebase thật)

- `backend/services/merchant_search_service.py`
  - `haversine_distance(lat1,lng1,lat2,lng2)` — great-circle km. (line 17)
  - `search()` : tính distance cho mỗi merchant, filter `radius_km`, sort. (line 91)
  - `nearby_search()` : **scan O(n) toàn catalog** (`limit=2000`), lặp `geo_filter` cho mỗi radius 5→10→20km (→ **3 full scan** nếu sparse). (line 193)
- `backend/database/models.py` — `Merchant.lat/lng` = `Column(Float)` thường, **KHÔNG có PostGIS**, **không spatial index**. CheckConstraint validate range.
- Quy mô: **~1681 merchants** (comment codebase). Một vùng VN (HN/HCMC).
- Output `SearchResult.distance_km` → hiện ra UI qua `to_dict()`.

**2 sub-problem tách biệt:**
| # | Vấn đề | H3 giúp? | Lời giải đúng |
|---|--------|----------|----------------|
| 1 | Distance **không thực tế** (đường chim bay) — pain user | ❌ KHÔNG | Routing engine / Matrix API |
| 2 | Query **chậm/không scale** (O(n) Python scan, 3× lặp) | ⚠️ Có thể, nhưng overkill | PostGIS `ST_DWithin` + GIST |

---

## Key Findings

### 1. H3 thực sự làm gì (và KHÔNG làm gì)

**Làm:**
- Phân bề mặt Trái đất thành lục giác phân cấp (15 resolution). [Uber H3 blog](https://www.uber.com/us/en/blog/h3/)
- `latlng_to_cell` → 1 cell ID; `grid_disk(k)` → mọi cell trong bán kính k hop.
- `grid_distance` = **số hop tối thiểu giữa 2 cell** (topology thuần).
- Edge length cố định theo resolution (bảng stats: res 15 ~0.5m, res 9 ~174m...). [H3 table](https://h3geo.org/docs/core-library/restable/)

**KHÔNG làm:**
- **Không tính road/driving distance hay travel time.** Cell không biết đường. [Medium hexagon-grid](https://medium.com/data-science/exploring-location-data-using-a-hexagon-grid-3509b68b04a2)
- Drive-time cần **isochrone/routing service ngoài**.

**Hạn chế:**
- **Pentagon distortion**: 12 ngũ giác mỗi resolution → `grid_distance`/`grid_ring` **có thể fail** khi cell bị pentagon chắn. [SO h3 griddistance](https://stackoverflow.com/questions/77281033/h3-cell-griddistance-limitations)
- Chỉ tính grid-distance giữa cell **cùng resolution, gần nhau**.

**→ Nếu thay Haversine bằng grid-distance: vẫn sai khác so với đường thực, lại thêm dependency + ETL (tính cell/merchant, chọn resolution) + edge case pentagon. Lời giải sai cho pain user.**

### 2. Routing = lời giải cho "thực tế"

**Self-host (free, không giới hạn):**
| Engine | Tốc độ | Linh hoạt | Ghi chú |
|--------|--------|-----------|---------|
| **OSRM** | ⚡ nhanh nhất (Contraction Hierarchies, ms) | Thấp (weight cố định) | Pick nếu chỉ cần A→B nhanh, weight chuẩn |
| **GraphHopper** | ≈ OSRM route ngắn | Cao (custom weight, CH+LM) | Cân bằng tốc độ/linh hoạt, RAM thấp |
| **Valhalla** | Nhanh, linh hoạt | Rất cao (Costing model) | Dùng bởi Mapbox; multi-modal tốt |

[Routing engine comparison](https://mapsi.dev/developers/routing-engine-comparison), [GIS-OPS FOSS overview](https://github.com/gis-ops/tutorials/blob/master/general/foss_routing_engines_overview.md)

→ Self-host cần **extract OSM Việt Nam** (Geofabrik, ~1-2GB), build graph 1 lần. Query sub-ms. Phù hợp nếu volume cao / muốn full control.

**Managed Matrix API (no-ops):**
| API | Pricing | Giới hạn/request | Free? |
|-----|---------|-------------------|-------|
| **OpenRouteService** | Free tier hào phóng | **3.500 locations (50×50)/req**, 350m snap | ✅ Có |
| Mapbox | $1.20–2.00/1K (volume) | 25×25, 30 req/min | Freemium |
| Google Maps | **$5/1.000 elements** | 25×25, 60K elem/min | Free cap mới (3/2025) |

[ORS restrictions](https://openrouteservice.org/restrictions/), [Google DM billing](https://developers.google.com/maps/documentation/distance-matrix/usage-and-billing), [Mapbox pricing](https://www.mapbox.com/pricing)

→ **Break-even** self-host vs managed: ~vài trăm nghìn request/tháng. Catalog 1681 + traffic demo → ORS free tier dư.

### 3. H3 vs PostGIS cho DB-side query (khi cần efficiency)

- **PostGIS**: `geography(Point,4326)` + `GIST` index → `ST_DWithin(geom, ::geography, meters)` = **O(log n)**, 1 dòng SQL, distance chính xác great-circle. Fix chuẩn cho "nearby query" trong Postgres. [h3-pg #165](https://github.com/postgis/h3-pg/issues/165) (discuss H3 làm **pre-filter** trước PostGIS — tức PostGIS mới là core).
- **H3**: sinh để **pre-filter dataset lớn** trước op đắt, **aggregation phân cấp đa vùng**, bucket nhất quán toàn cầu. [Rust Proof Labs](https://blog.rustprooflabs.com/2022/04/postgis-h3-intro)
- **Overkill khi:** catalog nhỏ, query point-in-radius/nearest-neighbor đơn giản, cần distance chính xác (H3 xấp xỉ cell). → **Đúng case hiện tại (1681 merchant).**

### 4. Hybrid pattern (đúng đắn cho geo search)

```
candidate pool (DB, ST_DWithin + index)   ← O(log n), great-circle
        │  top-K (vd 30)
        ▼
routing matrix (1 origin × K dest)        ← km + phút thực tế
        │
        ▼
re-rank theo (relevance, driving_min)     ← ETA có nghĩa cho user
```

H3 chỉ nhập cuộc ở **pha analytics/region bucketing**, không ở core distance. [Making geo joins faster w/ H3](https://news.ycombinator.com/item?id=46898473)

---

## Comparative Analysis

| Tiêu chí | Haversine (hiện tại) | H3 (cell distance) | PostGIS ST_DWithin | Routing (OSRM/ORS) |
|----------|----------------------|--------------------|--------------------|--------------------|
| Thực tế đường bộ | ❌ chim bay | ❌ vẫn hình học | ❌ vẫn chim bay (nhưng *đúng* chim bay, indexed) | ✅ **km + phút thực** |
| DB-side / scale | ❌ Python O(n) | ⚠️ cần ETL cell | ✅ O(log n) | N/A (service ngoài) |
| Độ phức tạp thêm | 0 | Cao (ext/ETL/resolution/pentagon) | **Thấp** (1 migration) | TB (1 service + cache) |
| Giải đúng pain user | ❌ | ❌ | ⚠️ phần efficiency | ✅ **Đúng pain** |
| Phù hợp quy mô 1.6k | — | Overkill | ✅ Tuyệt vời | ✅ Cần cho "thực tế" |

---

## Implementation Recommendations

### Pha 1 — Routing cho distance thực tế (GIẢI PAIN USER)

**Mục tiêu:** `distance_km` + `driving_min` thật; ETA hiện UI.

**Chọn engine:**
- **Nhanh nhất để thử:** **OpenRouteService Matrix** (free, 50×50/req, HTTP). 0 ops.
- **Production / volume cao:** **OSRM self-host** + extract VN (Geofabrik). Sub-ms, không giới hạn.

**Flow (đắp lên code hiện tại, YAGNI):**
1. `nearby_search` giữ Haversine để **coarse filter** → top ~30 candidate trong radius.
2. Gọi **matrix(1 origin × 30 dest)** → `driving_km`, `driving_min` mỗi merchant.
3. Re-rank theo (relevance, `driving_min`); surface ETA "~8 phút đi xe".
4. **Cache** key = `(origin_cell_res9, merchant_id)` (merchant tĩnh → hit-rate ~100% sau warmup). Hoặc cache theo (origin_latlng round 3 decimals, merchant_id).

**Code touchpoints:**
- **Mới** `backend/services/routing_service.py` — client OSRM/ORS + cache (Redis hoặc DB table `route_cache(origin_key, merchant_id, km, min)`).
- **Sửa** `merchant_search_service.py`:
  - `SearchResult` thêm `driving_min: float|None`; `to_dict()` thêm `"driving_min"`.
  - `nearby_search` cuối: enrich top-K qua `routing_service.matrix(...)`.
- **Mới** config `ROUTING_PROVIDER` (`osrm`/`ors`), `OSRM_URL`, `ORS_API_KEY` (qua settings, không hardcode).
- Migration: table `route_cache` (nếu cache DB).

**Quick start OSRM (docker, extract VN):**
```bash
# 1 lần: build graph VN
docker run -t -v $(pwd)/osrm-data:/data osrm/osrm-backend osrm-extract -p /opt/car.lua /data/vietnam-latest.osm.pbf
docker run -t -v $(pwd)/osrm-data:/data osrm/osrm-backend osrm-partition /data/vietnam-latest.osrm
docker run -t -v $(pwd)/osrm-data:/data osrm/osrm-backend osrm-customize /data/vietnam-latest.osrm
# chạy:
docker run -p 5000:5000 -v $(pwd)/osrm-data:/data osrm/osrm-backend osrm-routed --algorithm mld /data/vietnam-latest.osrm
# matrix: GET /table/v1/driving/{lng,lat};{lng,lat},...?annotations=duration,distance
```

**ORS Python (matrix):**
```python
# pip install openrouteservice
from openrouteservice import Client
cl = Client(key=ORS_KEY)  # via settings, KHÔNG hardcode
res = cl.distance_matrix(
    locations=[[lng, lat], *[m.lng, m.lat] for m in candidates],
    sources=[0], metrics=["distance", "duration"], units="km",
)
# res['distances'][0][1:]  → km;  res['durations'][0][1:]  → giây
```

### Pha 2 — PostGIS cho efficiency (CHỈ KHI scale hoặc scan chậm)

**Mục tiêu:** bỏ scan O(n) × 3 của `nearby_search`; push xuống DB indexed.

**Steps:**
1. Enable PostGIS extension.
2. Migration: thêm `geom = geography(Point,4326)` computed từ `lat/lng` + **GIST index**. Backfill.
3. Repo: `nearby_search` dùng `ST_DWithin(:geom, merchants.geom, :meters)` + `ST_Distance(...) AS distance_km` → bỏ Python loop.
4. Loại bỏ logic auto-expand 5→10→20 (DB-side radius query rẻ, mở rộng = đổi 1 tham số).

→ **Đơn giản hơn H3 rất nhiều**, fix đúng vấn đề efficiency mà không thêm khái niệm cell/resolution.

### Pha 3 — H3 (CHỈ cho analytics, optional)

Chỉ khi: mở rộng đa tỉnh/đa quốc gia, dashboard vùng, surge pricing, hoặc muốn "cell nào chưa có quán phở". Lúc này H3 + `h3-pg` mới có giá trị riêng. **Không dùng cho core distance.**

---

## Risks & Pitfalls

| Risk | Mitigation |
|------|------------|
| OSRM extract VN nặng / build chậm | Dùng Geofabrik `vietnam-latest.osm.pbf`; build 1 lần, docker volume persist |
| Routing latency adds TTFT | Cache theo cell (merchant tĩnh); matrix 1×N 1 call; async/parallel với LLM search task |
| ORS free tier rate-limit | Cache + fallback Haversine khi rate-limit/timeout; raise 429 → degrade gracefully |
| Distance "thực" lệch kỳ vọng (sông/highway) | Đây là *tính năng*, không bug — đúng hơn cho user |
| PostGIS migration phức tạp | Lùi Pha 2 cho đến khi scan thực sự bottleneck (đo benchmark, KHÔNG đoán) |
| H3 pentagon distortion nếu lỡ dùng | VN ở vĩ độ thấp, ít gặp, nhưng `grid_distance` có thể fail → phải try/except |
| Over-engineering | Tuân YAGNI: Pha 1 đủ cho demo GSM; Pha 2/3 chỉ khi metric yêu cầu |

---

## Security Considerations

- **API key routing** (ORS/Mapbox/Google) → qua `get_settings()`, **KHÔNG hardcode**, KHÔNG commit. Tôn trọng hook `@@PRIVACY_PROMPT@@`.
- OSRM self-host → expose chỉ nội bộ (không public port); rate-limit nội bộ.
- Origin lat/lng = vị trí user → **PII vị trí**, không log raw, redact khi trace.

---

## Verification (nếu implement)

1. Benchmark trước/sau: catalog 1681, query nearby — so `nearby_search` latency + accuracy distance vs Google Maps (gold standard).
2. Smoke: query "quán phở gần Cầu Giấy" → `distance_km`/`driving_min` khớp Google Maps ±15%.
3. Cache hit-rate ≥ 95% sau 100 query lặp cell.
4. Unit: `routing_service.matrix` mock + cache hit/miss; `nearby_search` enrich driving_min.
5. Fallback: kill OSRM/ORS → degrade Haversine, KHÔNG 500.

---

## Resources & References

### H3
- [Uber H3 blog](https://www.uber.com/us/en/blog/h3/) | [H3 core site](https://h3geo.org/) | [Traversal API (grid_disk/grid_distance)](https://h3geo.org/docs/api/traversal/) | [Cell stats table](https://h3geo.org/docs/core-library/restable/)
- [r/gis: H3 → drive-time cần isochrone ngoài](https://www.reddit.com/r/gis/comments/1sumk4w/) | [SO: grid_distance limitations](https://stackoverflow.com/questions/77281033/h3-cell-griddistance-limitations)
- [h3-pg #165: H3 làm pre-filter trước PostGIS](https://github.com/postgis/h3-pg/issues/165) | [Rust Proof Labs: PostGIS + H3 intro](https://blog.rustprooflabs.com/2022/04/postgis-h3-intro) | [HN: geo joins faster with H3](https://news.ycombinator.com/item?id=46898473)

### Routing
- [OSRM](http://project-osrm.org/) | [GraphHopper](https://www.graphhopper.com/) | [Valhalla](https://github.com/valhalla/valhalla) | [GIS-OPS FOSS routing overview](https://github.com/gis-ops/tutorials/blob/master/general/foss_routing_engines_overview.md) | [mapsi.dev engine comparison](https://mapsi.dev/developers/routing-engine-comparison)
- [Geofabrik VN extract](https://download.geofabrik.de/asia/vietnam.html)
- [ORS restrictions](https://openrouteservice.org/restrictions/) | [Google Distance Matrix billing](https://developers.google.com/maps/documentation/distance-matrix/usage-and-billing) | [Mapbox pricing](https://www.mapbox.com/pricing)

### PostGIS
- [PostGIS ST_DWithin docs](https://postgis.net/docs/ST_DWithin.html) | [h3-pg ext](https://github.com/zachasme/h3-pg)

---

## Unresolved Questions

1. **Scale thật:** traffic dự kiến (QPS nearby)? Nếu thấp (< 50/min) → ORS free đủ; nếu cao → OSRM self-host. Cần user xác nhận volume.
2. **Modal giao thông:** ưu tiên *car* hay *motorbike*? VN = motorbike chủ đạo, nhưng OSRM default `car.lua`. GraphHopper/Valhalla linh hoạt custom profile hơn cho bike.
3. **ETA hay km?** Đề xuất ưu tiên **phút đi xe** cho UX food discovery (HPG traffic). User confirm?
4. **H3 có case analytics riêng** (dashboard vùng GSM) không? Nếu có → Pha 3 đáng làm song song; nếu không → bỏ hoàn toàn H3.
5. **Geolocation accuracy hiện tại** (FE) có đủ tin để routing không? Desktop IP geo lệch km → routing trên origin sai cũng sai. Có thể cần snap origin về cell trung bình khu vực.
