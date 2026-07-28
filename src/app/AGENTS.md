# OCI Enterprise AI Chat — contributor guide

## Test and development
Use the scripts start_local.sh to start the needed program.

## Scope and working directory

This workspace contains three independent deliverables:

- `chat/` is the OCI Enterprise AI Chat application. Its actual Next.js project
  root is **`chat/files/`**; run Node, lint, build, and test commands there.
- `ui/html/` is a small standalone static HTML/CSS/JavaScript UI. It has no
  package manifest or shared runtime with the Next.js app.
- `rest/` is a Python/FastAPI service that exposes a LangGraph ReAct agent
  through a small LangGraph-compatible threads/runs API. It has its own Python
  dependencies and deployment scripts; it is not currently imported or called
  by the Next.js client.

The Next.js-specific sections below concern `chat/files/`. `chat/README.md` is
the operator-facing guide for that application; update it when changing its
user-facing configuration or OCI deployment behavior. Document `rest/`
configuration and deployment changes alongside that service when it gains a
dedicated operator guide.

## MCP sample server (`mcp_server/`)

`mcp_server/` is a small standalone FastMCP service, separate from both the
chat UI and the REST service. Run it from that directory with `start_local.sh`.
Its `get_dept` tool deliberately returns the four fixed rows from Oracle's
classic `DEPT` sample table (10/ACCOUNTING, 20/RESEARCH, 30/SALES, and
40/OPERATIONS); it must not require database credentials or make a database
connection. Keep its tool results JSON-serializable and deterministic. After
changing this service, syntax-check `mcp_server.py` and use the JSON-RPC
examples in `mcp_server/MCP_SERVER.md` to exercise its public tool contract.

## Architecture

The app is a Next.js 16 App Router application using React 19 and MUI 7.
Browser code is deliberately concentrated in `src/app`, while OCI credentials
and signing remain on the server.

```text
browser page/components
  -> useChat -> services/genaiAgentsService -> /api/* routes
  -> OCI GenAI Responses / stores, or MCP JSON-RPC servers

middleware (optional IDCS SSO) protects both UI and API routes
```

Key ownership:

- `src/app/page.js` is the main chat shell: model selection, theme/UI settings,
  sidebar, auth UI, and composition of the chat components.
- `src/app/hooks/useChat.js` owns exchange state, streaming-chunk handling,
  cancellation, persistence, widgets, user approvals, and the client-side
  function-call continuation loop.
- `src/app/services/genaiAgentsService.js` builds response payloads (base/user
  prompts, RAG, native tools, custom MCP tools) and consumes newline-delimited
  JSON from `/api/responses`.
- `src/app/services/conversationStorage.js` is a localStorage-backed cache and
  index for conversation metadata. OCI remains the source for conversation
  items.
- `src/app/components/chat/` renders input, messages, sources, tool/activity
  chips, approvals, reasoning, markdown, and attachments.
- `src/app/components/settings/` persists UI, prompts, memory, tool, and flow
  settings in localStorage. `ToolsTab.js` and `ToolForm.js` own tool setup.
- `src/app/components/widgets/` implements the original `§§` widget grammar;
  `widgets/v2/` implements the composable `@@widget … @@` grammar. Keep parser,
  prompt, registry, and renderer in sync when adding a widget.
- `src/app/utils/` contains message adapters/parsers and the prompt text.
  `baseSystemPrompt.js`, `widgetInlinePrompt.js`, and
  `widgetLayoutPrompt.js` affect model output contracts.
- `src/app/lib/` is server-safe/shared infrastructure: OCI auth/signing,
  proxying, IDCS/MCP OAuth, logging, and the read-only SQL guard.

## LangGraph REST service (`rest/`)

`rest/` is an independently deployed Python service. Run Python, dependency,
and service commands from `rest/`; do not use the Next.js package manifest for
it. `requirements.txt` provides its runtime dependencies (FastAPI/Uvicorn,
LangGraph/LangChain, OCI SDKs, Oracle DB, and MCP adapters). The provided
`install.sh`, `start.sh`, and `build.sh` assume the surrounding Compute helper
scripts and environment; `start.sh` activates `myenv` and defaults to port
8080. For local development, use an isolated virtual environment and run
`uvicorn rest:app` only after supplying its required environment configuration.

Ownership and request flow:

```text
LangGraph-compatible client
  -> rest.py FastAPI threads/runs endpoints (SSE or wait)
  -> AgentRuntime / LangGraph ReAct graph in agent.py
  -> optional MCP tools plus local vector-store and NL2SQL/Oracle DB tools
  -> OCI GenAI, OCI control-plane, MCP server, and Oracle Database
```

- `rest.py` owns the FastAPI application, bearer/User authentication, an
  in-memory per-thread message store, and the `/threads/{id}/runs/stream` SSE
  and `/runs/wait` contracts. It also exposes `/health` and `/ready` and mounts
  the configuration router.
- `agent.py` builds and atomically reloads the LangGraph ReAct agent. It
  discovers MCP tools at startup, forwards the original user authorization
  header (or an explicitly configured static bearer token), filters invalid
  empty tool parameter names, and turns tool failures into agent-visible
  structured results. Agent initialization retries MCP connection attempts, so
  keep startup/reload behavior in mind when editing it.
- `search.py` owns optional local tools: OCI Responses file search and OCI
  NL2SQL followed by direct Oracle Database execution. Tool availability is
  determined when the agent graph is built from the configured vector/semantic
  store IDs; configuration changes must reload the graph.
- `config.py` owns effective configuration, `/config/parameters`, dynamic
  LOV lookups (models, vector stores, semantic stores), and reload callbacks.
  It reads environment defaults and can persist editable values to
  `APP_CONFIG_FILE` (default `rest/config.json`).

### REST service security and compatibility rules

- Treat `rest/config.json` as a local secret-bearing runtime file: it can hold
  deployment-specific IDs. Never commit it, an `APP_CONFIG_FILE`, virtual
  environments, service logs, credentials, or OCI private configuration. Do
  not print tokens, authorization headers, database passwords, generated SQL
  containing sensitive values, or full tool arguments. MCP bearer credentials
  are accepted only from the individual Responses request tool definition and
  must not be persisted in REST configuration.
- `rest.py` currently validates `Bearer` tokens with the configured IDCS
  `/oauth2/v1/userinfo` endpoint and propagates the original header to MCP.
  Preserve this distinction from the `User <identity>` development/header form;
  do not weaken endpoint authentication merely to simplify local testing.
- Thread state is process-local and non-durable. It is serialized per thread by
  an `asyncio.Lock`, but it is not shared across workers or restarts. Preserve
  this limitation or introduce a deliberate durable/shared store before running
  multiple replicas.
- Keep the LangGraph-style SSE shape (`data: {"messages": {id: message}}`),
  monotonic message IDs, `/runs/wait` final-message payload, and error event
  behavior compatible with the intended client when editing stream code.
- The database tool generates SQL with OCI NL2SQL and executes it directly.
  Unlike `chat/files/src/app/lib/sqlGuard.js`, it has no local read-only SQL
  guard. Do not broaden it, add write-capable credentials, or expose it to
  untrusted callers without first adding a restrictive SQL validation and tests.
- Keep OCI signing and all auth material server-side. `AUTH_TYPE` selects
  Instance Principal or Resource Principal. Required secret/runtime values also
  include `PROJECT_OCID`/`TF_VAR_project_ocid`, `TF_VAR_compartment_ocid`, and,
  where applicable, `IDCS_URL`, DB credentials, vector-store, and semantic-store
  IDs. REST MCP endpoints are supplied only in each Responses request's `tools`
  array; do not add a configured service-wide MCP endpoint.
- Configuration writes mutate local process state and then rebuild the agent.
  Preserve validation, locking, redaction, and reload semantics when adding
  fields. Dynamic LOV requests may call OCI, so they require usable principal
  authentication and region/project configuration.

### REST service verification

There is no committed Python test suite yet. At minimum, syntax-check changed
modules with the configured interpreter and manually exercise `/health`, an
authenticated `/threads` request, and the affected `/config/*` or run endpoint
against safe non-production configuration. Do not make live OCI, MCP, or
database calls as a substitute for unit tests; add focused tests for changes to
authentication, stream serialization, SQL execution, or configuration reload.

## API boundaries and invariants

All `src/app/api/**/route.js` handlers are Next route handlers. Keep vendor
credentials, request signing, OAuth client secrets, and raw OCI calls in these
handlers or `src/app/lib`; never move them to a client component.

- `/api/responses` streams OCI Responses SSE as newline-delimited JSON for the
  client. It supports native OCI MCP execution, tool/approval state, source
  enrichment, optional Langfuse, and the multi-agent `/v1` endpoint. Preserve
  its `done`, `response_id`, `trace`, tool-call, and incomplete-response events
  when editing either end of the stream. `maxDuration` is five minutes.
- `/api/conversations`, `/api/files`, and `/api/vector-stores` proxy OCI
  conversations/files/vector-store CRUD. Conversation endpoints retain
  compatibility probes for both `/openai/v1` and `/v1`.
- `/api/semantic-stores` uses OCI's control plane. Selected semantic-store IDs
  are forwarded to the REST service, which generates and executes read-only SQL
  through the store's Database Tools query connection.
- `/api/mcp` is the JSON-RPC proxy for discovery, tests, and client-delegated
  calls. It supports API key, bearer, client-credentials OAuth, and interactive
  OAuth. Do not log tokens, secrets, or full sensitive tool arguments.
- `/api/mcp/oauth/**` implements OAuth 2.1 + PKCE. Tokens are signed httpOnly
  endpoint-scoped cookies; refresh-token minting uses a global single-flight
  cache because rotating IDCS refresh tokens must not be used concurrently.
- `/api/auth/**` plus `src/middleware.js` implement optional IDCS SSO.
  `/ready` and `/health` intentionally bypass authentication for OCI health
  checks.

Use `ociRequest()` from `src/app/lib/oci-proxy.js` for normal OCI calls. It
selects the correct host/headers and signs requests. Multipart uploads must use
its binary-body path, which preserves the bytes while signing. OCI auth selects
Resource Principal, then Instance Principal, else the local OCI config file.

## State and compatibility contracts

Many settings are browser-local, not server-persisted. Existing keys include
`uiSettings`, `selectedModel`, `systemPrompt`, `widgetsEnabled`,
`conciseEnabled`, `aiSettings`, `nativeToolsEnabled`, `mcpServers`,
`enabledTools`, `ragVectorStoreIds`, `nl2sqlSemanticStoreIds`, and
`customAgentFlows`. Preserve old keys or add an explicit migration when changing
their shapes.

Custom MCP server credentials configured in the UI may be stored in browser
localStorage; do not assume they are safe for a multi-user production design.
Prefer server-side environment configuration for production-owned secrets.

`NEXT_PUBLIC_*` values are bundled into client code. Only expose public URLs or
non-secret identifiers through them.

## Configuration

Required OCI deployment values are `OCI_REGION`, `OCI_COMPARTMENT_ID`, and
`OCI_GENAI_PROJECT_ID`. Local authentication uses `OCI_CONFIG_FILE` and
`OCI_CONFIG_PROFILE`; deployment uses exactly one of
`USE_RESOURCE_PRINCIPAL=true` or `USE_INSTANCE_PRINCIPAL=true`.

Optional integrations include IDCS (`IDCS_DOMAIN_URL`, `IDCS_CLIENT_ID`,
`IDCS_CLIENT_SECRET`, `SESSION_SECRET`), Langfuse (`LANGFUSE_*`), and
`OCI_TRACE_FILE` for raw debug events.
Never commit `.env*`, OCI config files, trace files, tokens, or OCIDs intended
to stay private.

For hosted/subpath deployments, production assets contain a base-path placeholder.
`entrypoint.sh` copies the standalone app to `/tmp/app` and replaces it using
`APPLICATION_BASE_URL` (preferred) or `BASE_PATH`. Client links must use
`withBase()` / `useBaseRouter()` where a base path matters.

## Development workflow

From `chat/files/`:

```bash
npm install
npm run dev       # Next dev with Turbopack, port 3000
npm run lint      # eslint .
npm test          # Playwright; starts/reuses the dev server
npm run build     # production standalone build
npm run start     # run the production build
```

Playwright is Chromium-only. It keeps output outside the repository to avoid
Turbopack reloads during tests. The suite includes pure utility tests, API
validation/auth tests, UI smoke tests, offline MCP chaining tests, and optional
NL2SQL wiring tests (skipped unless its public MCP URL is configured). Prefer
the smallest relevant test file while iterating; run lint and the relevant
tests before handing off a change.

## Change guidelines

- Add models in `src/app/page.js`'s curated static model list; ensure any model
  requiring OCI's native response endpoint still selects the correct route.
- When changing streaming payloads, update both `/api/responses` and
  `useChat`/`genaiAgentsService`, plus their mocked SSE fixtures in tests.
- When adding an MCP authentication flow, preserve endpoint-scoped cookies,
  base-path-aware redirect URLs, and refresh-token single-flight behavior.
- Keep `sqlGuard.js` restrictive: it must allow one `SELECT`/`WITH` statement
  only. Any execution-path change needs a matching unit test.
- Keep `models-internal.js` and `tools-internal.js` free of internal endpoints,
  keys, or IP addresses on this public branch.
- Maintain the existing client/server split. Files with `"use client"` may use
  browser storage but must not import Node-only modules or secrets.
- Avoid changing `entrypoint.sh`, `next.config.mjs`, Dockerfiles, or the
  production asset-prefix scheme without testing a production build and a
  non-root base path.

## Deployment notes

`next.config.mjs` builds `output: 'standalone'`; `chat/files/Dockerfile` expects
the prebuilt standalone output and serves port 8080. The outer `chat/Dockerfile`
and shell scripts are legacy/compute deployment helpers and are not the normal
Next.js container path. Keep the `/ready` health endpoint working.
