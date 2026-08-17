# Session handoff — Mem0, pgvector, and unified Compose

Updated: 2026-08-17. This file intentionally contains no credentials.

## Current verified state

- Unified infrastructure is defined in `docker-compose.yml` and is running as
  Compose project `vsf-merchant-ai`.
- Healthy services: `db` (`pgvector/pgvector:pg17`), `redis`, `mem0`, and
  `mem0-dashboard`.
- Local endpoints: Mem0 API `http://localhost:8888`, dashboard
  `http://localhost:3000`, PostgreSQL `localhost:5432`, Redis
  `localhost:6381`.
- PostgreSQL contains logical databases `merchant_platform` and `mem0`; both
  have pgvector 0.8.6 enabled.
- Mem0 collection `memories` is `vector(384)`.
- Custom API image: `vsf-mem0:v2.0.18-custom.1`, OCI revision `e6c90498`.
- Dashboard image: `vsf-mem0-dashboard:v2.0.18-custom.1`.
- Direct authenticated verification passed: health/add/search returned
  HTTP 200/200/200 and search retrieved the newly stored memory.
- Final runtime logs contained no audited secret values and no vector dimension
  errors.

## Source and commits

- Application repository commit: `4d29651 feat(infra): unify Mem0 pgvector runtime`.
- Separate Mem0 checkout: `/home/minhnv63/Documents/mem0`.
- Mem0 branch: `feat/vsf-mem0-custom-runtime`.
- Mem0 compatibility commits:
  - `d7597cde`: omit unsupported OpenAI `response_format` for v-llm-v1 and
    install the checked-out Mem0 source in the production image.
  - `e6c90498`: configure pgvector with the 384-dimensional embedding size.

## Runtime environment contract

Docker Compose automatically reads the application repository's root `.env`
for interpolation. Secrets are injected at container creation and are not
baked into either image.

Required values:

```dotenv
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<secret>

LLM_BASE_URL=https://v-llm-core.uat.ntmh.vsf.services/gsm/v1
LLM_API_KEY=<secret>
LLM_MODEL_SMALL=v-llm-v1-small

RAG_EMBEDDING_BASE_URL=https://v-llm-core.uat.ntmh.vsf.services/gsm/v1
RAG_EMBEDDING_API_KEY=<secret>
RAG_EMBEDDING_MODEL=v-llm-v1-embed-medium
RAG_EMBEDDING_DIMENSIONS=384

ADMIN_API_KEY=<secret>
JWT_SECRET=<secret>
MEM0_DISABLE_RESPONSE_FORMAT=true
```

Optional image and port overrides are documented in `.env.example`.

Changing only `.env` does not require an image rebuild. Recreate affected
containers from the application repository:

```bash
docker compose up -d --force-recreate mem0 mem0-dashboard
docker compose ps
```

## Rebuilding the custom Mem0 image

Build while connected to public Wi-Fi because private Wi-Fi currently causes a
Docker Hub CA verification failure. From the separate Mem0 checkout:

```bash
cd /home/minhnv63/Documents/mem0
git status --short
git rev-parse --short HEAD
docker build \
  --build-arg MEM0_SERVER_VERSION=vsf-mem0-v2.0.18-custom.1 \
  --build-arg VCS_REF=<git-revision-from-command-above> \
  -t vsf-mem0:v2.0.18-custom.1 \
  -f server/Dockerfile .
```

For a new release, prefer a new immutable tag such as
`vsf-mem0:v2.0.18-custom.2`, then set `MEM0_IMAGE` in the application `.env` to
that tag. Recreate the service after building:

```bash
cd /home/minhnv63/Documents/GSM_project/VSF_Merchant_Management_AI
docker compose up -d --force-recreate mem0 mem0-dashboard
curl http://localhost:8888/api/health
```

The dashboard only needs rebuilding when its source changes:

```bash
cd /home/minhnv63/Documents/mem0
docker build \
  --build-arg MEM0_SERVER_VERSION=vsf-mem0-dashboard-v2.0.18-custom.1 \
  --build-arg VCS_REF=<git-revision> \
  -t vsf-mem0-dashboard:v2.0.18-custom.1 \
  server/dashboard
```

## Network behavior

- Public Wi-Fi: Docker Hub and dependency downloads work; internal v-llm-v1 is
  unavailable.
- Private Wi-Fi: v-llm-v1 LLM and embedding calls work; Docker Hub currently
  fails CA verification.
- Build/pull on public Wi-Fi, then run the provider smoke on private Wi-Fi.

## Important operational notes

- Do not rebuild merely to change credentials, URLs, model names, ports, or
  telemetry flags; update `.env` and recreate the containers.
- Changing `RAG_EMBEDDING_DIMENSIONS` or embedding model makes an existing
  vector table incompatible. Never drop a populated production table; migrate
  or reindex it. The Task 4 table was dropped only after confirming it was empty.
- The old `vsf_dev_b_postgres` and `vsf_dev_b_redis` containers were stopped,
  not deleted; their data was not removed.
- Task 4 is complete. Remaining larger-plan work includes existing document
  chunk reindexing into application pgvector, backend/frontend integration,
  Mem0 client integration, the planner/subagent pipeline, and Langfuse prompt
  and trace restructuring.
