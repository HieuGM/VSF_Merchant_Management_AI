# Setup Guide — cài nhanh trên máy mới

Cài lại toàn bộ stack VSF Merchant Management AI trên máy công ty. Nếu clone repo + copy 3 file (xem §2) thì **1 lệnh** là chạy được.

---

## 0. Không có git? (máy công ty chặn git)

Git **không bắt buộc** để chạy project — `setup.sh` không dùng git, project chỉ là files. Cách chuyển code sang máy công ty:

- **OneDrive sync (dễ nhất — đang dùng):** sign-in OneDrive trên máy công ty → folder `AI_Restaurant` tự sync (có sẵn code + `.env` + `data/`). Sau khi sync xong, **move folder ra khỏi OneDrive** (tránh sync đụng `node_modules`/env khi dev), rồi `bash scripts/setup.sh`.
- **ZIP + USB:** `bash scripts/pack-for-transfer.sh` → `AI_Restaurant-transfer.tar.gz` (sạch, đã loại node_modules/venv/cache, **giữ** code + `.env` + `data/`). Copy qua USB → giải nén.
- **Download ZIP từ GitHub:** nếu github.com mở được (chỉ cài git bị chặn) → repo → Code → Download ZIP. Vẫn phải copy `.env` + `data/` tay (gitignore).
- **Portable Git (không cần admin):** https://git-scm.com/download/win → bản "Portable" nếu vẫn muốn dùng git.

> Env conda `ai_restaurant` + `node_modules` **không** transfer qua file → `setup.sh` tạo lại bằng `environment.yml` + `npm install`. Chỉ cần source + 3 file ở §2.

---

## 1. Prerequisites (cài trước)

| Tool | Why | Note |
|---|---|---|
| **Docker Desktop** | Postgres (compose) | Win/Mac dùng Desktop; Linux dùng `docker` + `docker compose` plugin |
| **Miniconda** | Python env `ai_restaurant` | https://docs.conda.io/miniconda — sau khi cài chạy `conda init` rồi mở terminal mới |
| **Node.js 20+** | Frontend (Vite) | kèm npm |
| **Git** | Clone repo | |

---

## 2. ⚠️ Copy tay 3 file (KHÔNG có trong git)

Repo gitignore các file lớn/regenerable + secret. **Phải copy từ máy cũ sang máy mới** (USB / Google Drive / scp):

| File (tại repo root) | Size | Lý do |
|---|---|---|
| `.env` | nhỏ | **secret** — LLM keys (FPT_API_KEY, FPT_BASE_URL, FPT_MODEL_QWEN, FPT_MODEL_DEEPSEEK), DB creds |
| `data/profiles.jsonl` | ~24 MB | dataset merchant profiles (output của build pipeline) |
| `data/merchants_unique.jsonl` | ~2 MB | dataset merchants gốc |

> Không copy 3 file này → script sẽ báo lỗi ở bước import (kiểm tra có sẵn). Phần còn lại (code, `environment.yml`, `docker-compose.yml`) đều có trong git.

---

## 3. Cài (1 lệnh)

```bash
git clone <repo-url> AI_Restaurant && cd AI_Restaurant
# copy 3 file (§2) vào đây
bash scripts/setup.sh
```

Script tự động:
1. `conda env create -f environment.yml` → tạo env `ai_restaurant` (đúng 170 deps như máy cũ).
2. `docker compose up -d` → Postgres 18.
3. `alembic upgrade head` → tạo toàn bộ schema.
4. `python scripts/db/import_dataset.py` → nạp 1.625 merchant + profiles.
5. `cd frontend && npm install`.

> **Redis không bắt buộc** — app dùng memory-adapter mặc định (`cache_backend="memory"`). Health endpoint báo `redis: ok` mà không cần chạy Redis.

---

## 4. Chạy

```bash
# Backend (terminal 1)
conda activate ai_restaurant
cd backend && PYTHONUTF8=1 PYTHONPATH=. python -m uvicorn app.main:app --port 8000

# Frontend (terminal 2)
cd frontend && npm run dev      # → http://localhost:5173

# Check
curl localhost:8000/health      # mong đợi {"status":"ok","database":"ok","redis":"ok","llm_configured":true}
```

`llm_configured:true` = `.env` có key FPT. Frontend gọi thẳng `http://localhost:8000` (CORS đã bật).

---

## 5. Troubleshooting

| Lỗi | Fix |
|---|---|
| `conda: command not found` | Chạy trong Anaconda Prompt, hoặc `conda init bash` rồi mở terminal lại |
| `docker compose` not found | Linux: `sudo apt install docker-compose-plugin`; Win/Mac: mở Docker Desktop |
| Port 5432 đã dùng | Đổi port trong `docker-compose.yml` + `DB_PORT` trong `.env` |
| Alembic `TargetDatabaseNotUpToDate` | `cd backend && PYTHONPATH=. alembic upgrade head` lại |
| `llm_configured:false` | Thiếu key FPT trong `.env` — copy lại từ máy cũ |
| Timeout khi import | `PYTHONUTF8=1 PYTHONPATH=backend python scripts/db/import_dataset.py --chunk 500` (chunk nhỏ hơn) |
| crewai/LangChain xung đột | Đảm bảo cài đúng từ `environment.yml` (crewai==1.15.5 standalone) — KHÔNG `pip install langchain` |

---

## Unresolved
- Repo URL clone: dùng remote hiện tại (`https://github.com/HieuGM/VSF_Merchant_Management_AI.git`) hay internal của công ty?
- Nếu máy công ty chặn Docker Hub: cần registry nội bộ hoặc pull image `postgres:18-alpine` trước.
