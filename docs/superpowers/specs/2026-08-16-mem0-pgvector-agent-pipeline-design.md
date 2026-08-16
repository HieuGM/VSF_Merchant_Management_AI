# Mem0, pgvector, and Merchant Agent Pipeline Redesign

Date: 2026-08-16
Status: Approved design, pending written-spec review

## Goal

Replace the current NLU and hierarchical coordination pipeline with a smaller,
lower-latency agent flow backed by self-hosted Mem0. Consolidate application
data and policy vectors into PostgreSQL with pgvector, package the full runtime
in one Docker Compose project, and make Langfuse traces directly usable by
automatic evaluators.

The target request path is:

```text
user query
  -> Mem0 semantic memory retrieval
  -> one planner LLM call
      -> answer immediately, or
      -> one specialist, or
      -> 2-4 specialists in parallel -> synthesis
  -> persist chat response
  -> add the completed turn to Mem0 outside the critical response path
```

## Required Constraints

- Semantic routing, scope interpretation, and delegation are LLM decisions.
- Do not use regex, keyword matching, or specific case tables for semantic
  routing.
- Deterministic identity binding, authorization, validation, public-field
  projection, and tool allow-lists remain in application code.
- A specialist cannot delegate or hand work to another agent.
- Synthesis runs only when at least two specialists return results.
- A single specialist's response is the final response without another LLM
  call.
- Mem0 retrieval has no PostgreSQL chat-history fallback.
- Policy document chunks already exist. Re-embed those chunks; never recreate
  them from raw documents during this migration.
- Application schema changes are produced with Alembic autogenerate and then
  reviewed. Do not handwrite an Alembic revision.
- The application and Mem0 use the project's configured LLM endpoint and
  models. The Mem0 server must support an OpenAI-compatible custom base URL.
- Prompt content is managed and versioned in Langfuse, with no source-code
  prompt fallback.
- Preserve unrelated changes in the application worktree.

## System Boundaries

The design has four bounded parts:

1. **Unified runtime infrastructure** owns containers, networking, health
   checks, persistence, and configuration wiring.
2. **Application retrieval and schema** owns merchant relational data and
   policy chunks/vectors in the `merchant_platform` database.
3. **Mem0 service** owns semantic user memory in the separate `mem0` database
   and its short-term message-history volume.
4. **Merchant agent runtime** owns planning, specialist execution, synthesis,
   response persistence, and semantic Langfuse observations.

Application Alembic migrations never manage Mem0's tables. Mem0 never becomes
the canonical store for chat UI or audit records.

## Unified Docker Compose

One Compose project contains:

- `db`: local image `pgvector/pgvector:pg17`;
- `redis`: Redis 7;
- `mem0`: the project-owned, versioned custom Mem0 REST image;
- `mem0-dashboard`: a pinned dashboard image built from the same clean Mem0
  source revision;
- `backend`: the FastAPI application;
- `frontend`: the application frontend.

The database container initializes two logical databases on a fresh volume:

- `merchant_platform` for application tables and policy embeddings;
- `mem0` for Mem0-managed storage.

The initialization script enables `vector` in every database that needs it.
Creating databases and enabling PostgreSQL extensions are bootstrap concerns,
not Alembic model diffs. The script must be idempotent for fresh initialization,
while Alembic remains the only application schema-version mechanism after
bootstrap.

Containers communicate through Compose service DNS. The backend calls Mem0 at
its internal service URL, not `localhost`. Host port `8888` may remain available
for local diagnostics; production exposure is configurable and does not expose
PostgreSQL or Redis publicly by default.

Persistent volumes cover PostgreSQL, Redis, and Mem0's `/app/history` path.
Health checks gate service startup: database readiness precedes migrations,
Mem0 waits for its database, and the backend waits for database, Redis, and
Mem0 health.

No production service installs packages or runs source reload at container
startup. Images contain pinned dependencies and start immutable application
artifacts.

## Custom Mem0 Image

The Mem0 image is built from the local Mem0 source repository rather than the
official runtime image. Before implementation, the four currently uncommitted
Mem0 source changes are discarded as explicitly authorized, and work begins
from the clean upstream revision already used by the local environment.

The custom change is isolated in the Mem0 repository and committed separately
from this application. It provides:

- OpenAI-compatible custom LLM base URL, API key, and model configuration;
- a separately configured embedding base URL, API key, model, and dimension;
- environment-driven server configuration with no credentials in source or
  logs;
- pinned `mem0ai==2.0.18` behavior for reproducible builds;
- production startup without reload or runtime package installation.

Configuration maps the same project settings into Mem0:

```text
Mem0 LLM base URL  <- LLM_BASE_URL
Mem0 LLM API key   <- LLM_API_KEY
Mem0 LLM model     <- LLM_MODEL_SMALL
Mem0 embed URL     <- RAG_EMBEDDING_BASE_URL
Mem0 embed API key <- RAG_EMBEDDING_API_KEY
Mem0 embed model   <- RAG_EMBEDDING_MODEL
Mem0 dimensions    <- RAG_EMBEDDING_DIMENSIONS
```

The resulting image receives an immutable custom version such as
`vsf-mem0-v2.0.18-custom.1`. Compose consumes the full project-owned image
reference through `MEM0_IMAGE`; it does not use `latest`. The image is locally
tested, tagged, and pushed to the user's authenticated registry only after the
custom commit passes its tests. Registry credentials are never copied into the
image or repository.

## PostgreSQL and pgvector Migration

### Application Schema

`PolicyDocumentChunk` gains:

- `embedding vector(RAG_EMBEDDING_DIMENSIONS)`;
- `embedding_model`, recording the model that produced the vector;
- an HNSW cosine-distance index declared in SQLAlchemy metadata.

The `pgvector` Python package is a direct dependency because the SQLAlchemy
model and query use it directly. The model is changed first, then the revision
is generated with `alembic revision --autogenerate`, reviewed for the vector
column and HNSW operator class, and applied with `alembic upgrade head`.

The vector dimension is a schema contract. Changing embedding dimensions later
requires a new model change, autogenerated migration, and complete reindex.

### Data Migration

The pgvector 17 database starts from a new volume; an existing PostgreSQL 18
data directory is never mounted into it. Application data is moved with a
PostgreSQL logical, data-only dump from the current PostgreSQL 18 source (or the
existing dump after it passes the same validation). The PostgreSQL 18 client
performs both dump and restore. The fresh target schema is created by Alembic
first, and the restore excludes `alembic_version`. This avoids binary
data-directory incompatibility and prevents the old schema history from
overwriting the new one.

The logical restore is dry-run tested against PostgreSQL 17 before cutover. If
the source uses a PostgreSQL 18-only data representation or feature that cannot
load into 17, migration stops and reports the incompatibility; it does not
silently coerce data. This is the explicit compatibility gate for using the
already available pgvector 17 image.

Policy migration copies existing `policy_documents` and
`policy_document_chunks` rows as data. It preserves at least:

- document and chunk IDs;
- document relationship and chunk index;
- content and content hashes;
- section metadata and token counts.

A one-shot, resumable index command selects stored chunk content in batches,
calls the configured embedding endpoint, and updates only `embedding` and
`embedding_model`. It does not invoke crawlers, raw document loaders, parsers,
or chunkers. Re-running it skips rows already indexed by the target model and
dimension unless an explicit full reindex is requested.

Before Chroma is removed, verification compares the pre-migration and
post-migration document/chunk counts and hashes. Any count or content-hash
mismatch stops the migration.

### Retrieval

Policy retrieval remains hybrid:

1. Existing application BM25 ranks the stored chunk text.
2. A direct SQLAlchemy pgvector cosine query ranks stored embeddings.
3. Reciprocal-rank fusion combines the two ranked lists.
4. The service hydrates the selected rows from PostgreSQL.

There is no second vector-store abstraction. After retrieval regression tests
pass, remove Chroma configuration, persistence, client code, and dependencies.
The PostgreSQL rows are the sole policy content and vector source.

## Mem0 Memory Contract

PostgreSQL chat messages remain canonical for UI history and audit. Mem0 is a
derived semantic memory service used to provide compact, relevant context to
the planner.

Identity is mapped consistently:

```text
user_id  = authenticated application principal
agent_id = merchant-advisor:{owner_merchant_id}
run_id   = application chat session ID
```

For each request, the backend calls Mem0 search with only the current user
query plus `user_id` and `agent_id`. Search omits `run_id`, allowing relevant
memory across that user's sessions for the same merchant advisor. The result is
bounded to the top 3-5 memories and passed to the planner as a clearly marked
memory context.

An empty successful result is valid and the planner continues with empty memory
context. A timeout, authentication error, or unavailable Mem0 service fails the
request with a stable service error; the application does not concatenate or
query PostgreSQL history as a fallback.

After the final answer is persisted and ready for the client, the latest user
and assistant pair is submitted to Mem0 with the complete identity tuple. This
write is best-effort and outside the critical response path. Failure is traced
and logged without invalidating an already completed chat response. No full
conversation concatenation is sent to `add()`.

## Agent Runtime

### Planner

The planner receives:

- the current user query;
- the bounded Mem0 results;
- owner identity/context that is safe for planning;
- concise capability contracts and decision rules.

It has no tools and makes exactly one LLM call. Its strict output is one of:

```json
{"mode": "respond", "answer": "..."}
```

or:

```json
{
  "mode": "delegate",
  "tasks": [
    {"capability": "owner", "instruction": "..."}
  ]
}
```

Allowed capabilities are `owner`, `market`, `policy`, `review`, and `cohort`.
The delegate form contains 1-4 bounded, independently executable tasks. Output
is validated once with a discriminated Pydantic union. Invalid output fails
safely; there is no JSON repair LLM call and no legacy coordinator fallback.

The prompt describes general capability and evidence boundaries. It contains no
catalog of specific user phrases, regexes, keyword routing rules, or duplicated
business cases. The planner may answer directly only when the supplied context
is sufficient and no tool evidence is required.

### Specialists

Each specialist has one stable capability contract, only the tools allowed for
that capability, and `allow_delegation=False`. A specialist can call several of
its own tools when its assigned task requires it, but cannot invoke another
agent or widen its scope. Its output is a bounded, self-contained user-facing
answer with supporting evidence, so the same contract works as the final answer
for a single task and as synthesis input for a parallel run.

The gateway remains the deterministic trust boundary. It binds owner-scoped
merchant IDs outside model arguments, validates typed inputs, enforces public
merchant allow-lists, and strips private/internal fields from outputs. The
current keyword-based `MerchantDataPolicy.query_decision` and other semantic
routing helpers are removed; authorization rules are not removed.

Execution has three paths:

- `respond`: return the planner's answer immediately;
- one delegated task: execute one specialist and return its answer directly;
- two to four delegated tasks: execute specialists concurrently, then call one
  tool-free synthesis agent.

The synthesis agent receives the user question and successful specialist
results. It cannot call tools or delegate. If one parallel branch fails, it
uses the successful evidence and clearly states the missing part. If every
branch fails, the request fails instead of asking synthesis to invent an
answer.

This replaces input preparation, rewritten-query generation, scope
classification, deterministic semantic routing, shadow/legacy/hierarchical
modes, coordinator delegation loops, evidence verifier handoffs, and
unconditional synthesis.

## Langfuse Prompt Management

The application runtime remains read-only for prompts and retrieves the
configured production label with SDK caching. Missing or unavailable prompts
fail the affected request; source-code prompt text is not used as fallback.

New prompt versions are created for:

- `merchant/planner`;
- `merchant/specialist-owner`;
- `merchant/specialist-market`;
- `merchant/specialist-policy`;
- `merchant/specialist-review`;
- `merchant/specialist-cohort`;
- `merchant/synthesis`.

Prompt templates use Langfuse variables and are compiled with bounded runtime
values. Every LLM observation links the exact Langfuse prompt object, name, and
version. Prompt authoring/push is a one-shot implementation or release action,
not application startup behavior. New versions are validated and evaluated
before the production label moves to them.

## Evaluation-First Langfuse Tracing

### Root Evaluation Surface

The canonical root observation is `merchant-advisor-flow` with type `agent`.
Automatic decorator capture is disabled. Application code explicitly records:

```text
root input  = original user message string
root output = final user-visible answer string
```

The returned API DTO remains unchanged where needed by the frontend, but it is
never used as the Langfuse root output. `trace_id`, `session_id`, `merchant_id`,
capabilities, status, duration, and execution mode live in first-class trace
attributes or metadata, not semantic input/output.

Response-quality evaluators can therefore target the root without preprocessing
transport JSON.

### Semantic Observation Tree

The canonical multi-agent trace is:

```text
merchant-advisor-flow                 agent
├── memory.search                     retriever
├── planner                           generation
├── specialist.owner                  agent
│   ├── merchant.get_owner_metrics    tool
│   └── merchant.get_owner_reviews    tool
├── specialist.policy                 agent
│   └── merchant.search_policy        tool
└── synthesis                         generation
```

Only executed nodes are present. `synthesis` is absent for planner responses and
single-specialist runs. Parallel branches receive explicit trace/parent context
so thread or task boundaries cannot create detached traces.

Observation payload contracts are:

| Observation | Input | Output |
| --- | --- | --- |
| Root agent | Raw user question text | Final answer text |
| Mem0 retriever | Current query text | Bounded relevant memories |
| Planner generation | Semantic query and memory context | Validated planner decision JSON |
| Specialist agent | Delegated instruction text | Specialist answer/evidence text |
| Tool | Validated tool argument object | Sanitized public result object |
| Synthesis generation | Question and successful specialist results | Final answer text |

Structured JSON is retained only where structure is the semantic artifact,
such as planner decisions and tool arguments/results. IDs, database sessions,
request wrappers, connection details, secrets, and raw exceptions never appear
in these input/output fields.

`trace_tool_invocation` creates a real Langfuse `tool` observation for every
gateway call. Tool names are stable, arguments are recorded after validation,
and output is the same sanitized projection seen by the specialist. Failures
use `level=ERROR` and a stable sanitized status message.

Each LLM generation records linked prompt name/version, model/provider,
temperature, usage, latency, and cost when the provider supplies them. Root
metadata contains only operational dimensions useful for filtering, such as
merchant, execution mode, capabilities, status, environment, and memory count.

Global `CrewAIInstrumentor` output is not canonical in the new pipeline and is
removed to prevent duplicated, low-level, JSON-heavy observations. The
application-authored semantic observations cover the required agent, model,
retriever, and tool boundaries.

Evaluator targeting is explicit:

- answer relevance and quality target the root trace;
- planner correctness targets `planner` generations;
- tool selection and argument correctness target `tool` observations;
- groundedness targets specialist or synthesis generations whose inputs contain
  the evidence used for their outputs.

Mem0 background writes use a separate maintenance observation linked by the
originating trace ID in metadata; they do not delay or extend the canonical
response trace.

The application trace API continues exposing its safe projection and does not
become a raw Langfuse payload proxy.

## Error Handling

- Mem0 search failure stops the request with a stable unavailable/authentication
  error and no history fallback.
- Zero Mem0 results is not an error.
- Invalid planner output fails after one validation attempt.
- One specialist failure in a multi-specialist run produces a partial,
  explicitly qualified synthesis from successful branches.
- All specialist failures fail the request.
- Tool authorization or validation errors remain fail-closed and are visible as
  sanitized tool errors.
- Synthesis failure fails the multi-specialist request; it does not fall back to
  concatenating worker outputs.
- Mem0 add failure after a completed response is non-fatal and observable.
- Prompt retrieval/compilation failure has no local fallback.
- Trace export failure does not roll back an already persisted chat response.

## Testing and Verification

### Infrastructure and Mem0

- Compose config resolves without missing variables and uses
  `pgvector/pgvector:pg17` plus an immutable `MEM0_IMAGE`.
- Fresh startup creates both logical databases, enables `vector`, and reaches
  healthy status for every service.
- Mem0 custom-image tests cover custom LLM and embedding base URLs without
  exposing credentials.
- A real smoke test adds and searches memory through the custom image.
- The built image records the expected custom version and is pushable/pullable
  from the selected registry.

### Schema and Retrieval

- SQLAlchemy metadata contains the vector column, model column, dimension, and
  HNSW cosine index.
- Alembic autogenerate produces the expected revision and a clean second
  autogenerate reports no schema drift.
- Upgrade succeeds on a fresh pgvector database.
- Data migration preserves policy document/chunk IDs, counts, ordering, content,
  and hashes.
- Reindex is batch-safe, resumable, idempotent, and never invokes chunking.
- Dense SQL retrieval, BM25 retrieval, RRF ranking, empty corpus, and embedding
  failures have unit/integration coverage.
- Retrieval regression uses the existing policy evaluation cases before Chroma
  code and data are removed.

### Runtime

- Planner `respond`, one-task, and multi-task decisions validate correctly.
- Invalid schema is rejected without repair or legacy fallback.
- No semantic route depends on regex, keyword matching, or case-specific code.
- One specialist causes one specialist execution and zero synthesis calls.
- Multiple specialists execute concurrently and cause exactly one synthesis
  call.
- Specialists have capability-scoped tools and cannot delegate.
- Gateway owner binding, allow-list, typed validation, and public projection
  security tests remain passing.
- Mem0 search uses the defined identity and current query without concatenated
  PostgreSQL history.
- Mem0 outage proves there is no PostgreSQL fallback.
- PostgreSQL chat persistence and Mem0 add receive the same completed turn.

### Langfuse

- Root input/output are strings containing exactly the user question and final
  answer.
- Root input/output contain no trace, session, request, or merchant wrapper.
- Every gateway call creates exactly one correctly parented tool observation.
- Parallel observations share one root and remain under their specialists.
- Direct, single-specialist, and multi-specialist topology matches the executed
  flow.
- Prompt name/version and model usage are linked to each generation.
- Secrets and prohibited internal fields are absent from trace payloads.
- A real short-lived smoke run flushes Langfuse, fetches the observations, and
  verifies the evaluation contracts.

## Migration and Release Order

1. Create the clean custom Mem0 commit, build its immutable image, and run Mem0
   custom endpoint tests.
2. Add the unified Compose topology, database bootstrap, health checks, and
   configuration contracts.
3. Add the SQLAlchemy vector model and direct dependency, autogenerate/review
   the Alembic revision, and verify a fresh upgrade.
4. Logically migrate application data, preserve existing chunks, and reindex
   them into pgvector.
5. Replace Chroma dense search with direct pgvector search while retaining BM25
   and RRF; run retrieval regression and remove Chroma.
6. Add the Mem0 client and identity contract, then implement the new planner,
   specialist, parallel, and conditional synthesis runtime.
7. Replace noisy automatic tracing with the semantic evaluation-first Langfuse
   hierarchy and tool observations.
8. Create and push new Langfuse prompt versions, run evaluator/smoke checks, and
   promote the verified versions.
9. Remove obsolete NLU, semantic routers, hierarchical coordinator paths, and
   their dead tests/configuration.
10. Run the complete backend, frontend, Compose, Mem0, pgvector, and Langfuse
    verification suite.
11. Push the verified custom Mem0 image and deploy Compose using its immutable
    digest or version tag.

Database backups and the previous deploy artifacts remain available for
deployment rollback. Runtime rollback is a version rollback, not an alternate
history/vector fallback inside the new request path.

## Out of Scope

- Re-chunking or recrawling policy documents.
- Sharing one schema or Alembic history between Mem0 and the application.
- A generic agent framework, dynamic agent registration, or specialist-to-
  specialist handoffs.
- A second vector database or compatibility adapter for Chroma.
- Runtime prompt creation or automatic prompt fallback.
- A durable background-job platform solely for Mem0 writes; the first version
  uses the application's existing process facilities and keeps PostgreSQL chat
  records canonical.
