# Setup Guide — chạy dự án trên máy mới (git-based)

Chuyển sang máy công ty qua **git** (không cần OneDrive/USB). Clone repo + copy 1 file `.env` + chạy **1 lệnh** là run được (backend + frontend + DB đầy đủ state).

---

## 1. Prerequisites (cài trước)

| Tool | Why | Note |
|---|---|---|
| **Git** | Clone repo | https://git-scm.com |
| **Docker Desktop** | Postgres 18 (compose) | mở Desktop để daemon chạy |
| **Miniconda** | Python env `ai_restaurant` | https://docs.conda.io/miniconda → `conda init` rồi mở terminal mới |
| **Node.js 20+** | Frontend (Vite) | kèm npm |

---

## 2. Chuyển code + dữ liệu qua git

```bash
git clone https://github.com/HieuGM/VSF_Merchant_Management_AI.git AI_Restaurant
cd AI_Restaurant
git checkout dev-a          # branch đang phát triển
```

Repo đã chứa sẵn mọi thứ cần chạy: **code + `environment.yml` + dataset (`data/*.jsonl`) + DB dump (`merchant_platform_full.dump`) + docs + scripts**.

> ⚠️ **Chỉ 1 file phải copy tay: `.env`** (secret — gitignored, không push lên git). Copy qua USB / Google Drive / ghi chú bảo mật. Cần các key: `POSTGRES_*`, `DB_HOST/PORT`, `FPT_API_KEY`, `FPT_BASE_URL`, `FPT_MODEL_DEEPSEEK`, `FPT_MODEL_QWEN`. Đặt `.env` ở repo root.
> DB creds mặc định `postgres/postgres` khớp sẵn `docker-compose.yml` → KHÔNG cần sửa nếu giữ mặc định.

---

## 3. Cài (1 lệnh)

```bash
bash scripts/setup.sh
```

Script tự động:
1. `conda env create -f environment.yml` → env `ai_restaurant` (đúng deps như máy cũ).
2. `docker compose up -d` → Postgres 18, đợi ready.
3. Check `.env` có sẵn (fail sớm nếu thiếu).
4. **Restore DB từ `merchant_platform_full.dump`** → đầy đủ: schema + 1.625 merchants + **124 user_profiles + 993 chat_sessions + 3223 chat_messages + preference/memory state** (clone y hệt DB máy cũ).
   - Nếu KHÔNG có dump → fallback: `alembic upgrade head` + import dataset (chỉ merchants, **không** có chat state).
5. `cd frontend && npm install`.

> **Redis không bắt buộc** — app dùng memory-adapter (`cache_backend="memory"`). `/health` báo `redis: ok` mà không cần chạy Redis.

---

## 4. Chạy

```bash
# Backend (terminal 1)
conda activate ai_restaurant
bash .start_backend.sh        # uvicorn :8000 (portable, dùng conda activate)

# Frontend (terminal 2)
cd frontend && npm run dev    # → http://localhost:5173

# Check
curl localhost:8000/health    # mong đợi {"status":"ok","database":"ok","redis":"ok","llm_configured":true}
```

`llm_configured:true` = `.env` có key FPT. Frontend gọi thẳng `http://localhost:8000` (CORS đã bật).

**Test:**
```bash
bash .run_all.sh              # compile + unit + integration (non-destructive)
bash .run_integ.sh            # chỉ integration
```

---

## 5. Troubleshooting

| Lỗi | Fix |
|---|---|
| `conda: command not found` | Anaconda Prompt, hoặc `conda init bash` rồi mở terminal lại |
| `docker compose` not found | Linux: `sudo apt install docker-compose-plugin`; Win/Mac: mở Docker Desktop |
| Port 5432 đã dùng | Đổi port trong `docker-compose.yml` + `DB_PORT` trong `.env` |
| `pg_restore` báo lỗi nhưng setup tiếp tục | setup.sh verify `merchants > 0` sau restore; nếu 0 → dump hỏng, re-dump máy cũ |
| Alembic `TargetDatabaseNotUpToDate` | `cd backend && PYTHONPATH=. alembic upgrade head` |
| `llm_configured:false` | Thiếu key FPT trong `.env` — copy lại từ máy cũ |
| crewai/LangChain xung đột | Cài đúng từ `environment.yml` (crewai==1.15.5 standalone) — KHÔNG `pip install langchain` riêng |
| FPT trả 401 (không phải 429) | Key exhausted — refresh `FPT_API_KEY` + restart backend |

---

## 6. Fallback — máy KHÔNG truy cập được GitHub

Git không mở được (máy công ty chặn github.com):
- **Download ZIP:** repo → Code → Download ZIP. Vẫn phải copy `.env` tay (gitignore).
- **OneDrive / USB:** `bash scripts/pack-for-transfer.sh` → `AI_Restaurant-transfer.tar.gz` (loại node_modules/venv/cache, giữ `.env` + `data/` + dump). Hoặc sign-in OneDrive sync folder.

> Docker Hub bị chặn? Cần pull sẵn `postgres:18-alpine` từ registry nội bộ trước `docker compose up`.

---

## 7. Tái tạo DB dump (lần sau chuyển máy)

Trên máy có DB muốn giữ:
```bash
docker exec gsm_merchant_postgres pg_dump -U postgres -Fc -d merchant_platform \
  > merchant_platform_full.dump        # -Fc = custom format, nén
```
Commit dump vào git (đã được track, KHÔNG còn bị gitignore). Máy mới `setup.sh` tự restore.

---

## Unresolved
- Repo clone ở máy công ty: remote hiện tại `https://github.com/HieuGM/VSF_Merchant_Management_AI.git` (GitHub) có bị chặn không? Nếu có → dùng §6 fallback.
- Máy công ty có chặn Docker Hub không? (cần `postgres:18-alpine`).
