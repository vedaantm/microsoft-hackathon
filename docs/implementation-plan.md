# Organization GenAI Token-Management Dashboard — Implementation Plan

Status: implementation completed through Phase 11 review. The application and local gateway exist; Azure resources are external to this repository, and the Azure Monitor provider remains an intentional placeholder.

---

## 1. Repository assessment

The repository now contains the implemented FastAPI backend, React frontend, local gateway, database migrations, seed fixtures, and test suites described by the later phases. This section is retained as the original assessment record rather than a claim that the repository is still an empty scaffold.

- Files and directories that already exist.
- Technologies already chosen (if any) that conflict with Section 7's proposed stack.
- Reusable work (auth scaffolding, CI config, existing FastAPI/React boilerplate).
- Architecture conflicts that would force a deviation from this plan.
- Recommended cleanup before Phase 0 starts (dead code, placeholder files, stale dependencies).

If the repo is genuinely empty, this section can be marked "confirmed fresh scaffold, no changes" and Phase 0 proceeds as written.

---

## 2. Assumptions

| # | Assumption | Why needed | Neal must confirm? | Recommended default |
|---|---|---|---|---|
| 1 | One APIM instance represents the whole organization for the MVP | Keeps mapping simple; multi-instance orgs are a non-goal | Yes | Single instance |
| 2 | Neal's APIM tier supports the Unified Model API and `llm-token-limit` / `llm-emit-token-metric` policies | These are preview features with tier restrictions | Yes | Confirm tier before Phase 9 |
| 3 | Application Insights (not a separate Log Analytics workspace) is the query target | Simplifies the telemetry provider's auth surface | Yes | Application Insights via `DefaultAzureCredential` |
| 4 | Member identity in the dashboard is independent of Entra ID for the MVP | Entra integration is explicitly deferred | No | Dev-only role-switch login locally; Entra planned, not built |
| 5 | SQLite is sufficient for local and Neal's initial test | Avoids provisioning a database server for a PoC | No | SQLite now, SQLAlchemy models portable to Postgres later |
| 6 | Cost estimates are informational only, never authoritative billing | Azure invoicing is out of scope | No | Every cost figure labeled "Estimated cost" in the UI and API |
| 7 | Metric-dimension cardinality limits apply per the current APIM documentation and may cap at a value below total member count for large orgs | Must be verified, not assumed | Yes | Verify actual limit before Phase 9; design for aggregate + detail split regardless |
| 8 | Streaming responses' token counts may be estimated rather than exact | Documented APIM behavior nuance | Yes | Store a `token_count_estimated` flag on usage records |
| 9 | Primary and secondary subscription keys are never both active in dashboard-facing UI simultaneously as "two members" | Prevents double-counting members | No | UI always displays one row per subscription ID regardless of which key was used |
| 10 | Neal will generate test traffic manually via scripts, not through a UI the dashboard team builds | Traffic generation is Neal's responsibility per Section 5 | No | Smoke-test scripts only, no traffic-generation UI |
| 11 | GitHub Actions CI runs without Azure credentials | Required so PRs don't need secrets | No | Azure steps are manual-trigger only, per Section 25 |
| 12 | Model pricing changes over time and must be versioned, not overwritten | Historical usage must price at the rate that was active then | No | `effective_from` / `effective_to` on `ModelConfiguration` |

Planning is not blocked on any of these; items marked "Neal must confirm" are flagged again in the risk register (Section 13) and the Azure handoff doc.

---

## 3. Architecture

**Components**

- **React dashboard** (Vite + TypeScript) — read-only presentation layer, role-aware.
- **FastAPI backend** — owns the database, authorization, aggregation, and the telemetry-provider abstraction. Never forwards or proxies LLM calls.
- **SQLite (later Postgres)** — organizational hierarchy, member↔subscription mapping, budgets, prices, alerts, audit log.
- **SeedTelemetryProvider** — synthetic usage fixtures for local dev.
- **AzureMonitorTelemetryProvider** — reads Application Insights via `DefaultAzureCredential`, normalizes to internal DTOs.
- **Azure API Management (Neal's resource)** — the actual GenAI gateway; outside this repo's runtime path.
- **Application Insights / Azure Monitor** — telemetry sink APIM writes to; the only thing the dashboard backend reads from Azure.

**Key flows**

1. **Local dashboard data flow**: React → FastAPI → SeedTelemetryProvider → synthetic DTOs → FastAPI aggregation/authorization → React.
2. **Azure production/test data flow**: Member → APIM (subscription key) → LLM backend → APIM → Application Insights → AzureMonitorTelemetryProvider → FastAPI normalization/mapping → React. The dashboard never sits in this live request path.
3. **Member-subscription mapping flow**: Azure telemetry arrives keyed by APIM subscription ID → backend looks up `MemberSubscription.apim_subscription_id` → resolves Member → Team → Department → Organization → attaches all four IDs to the normalized usage record.
4. **Key-rotation flow**: Neal rotates a key in APIM → subscription ID is unchanged → dashboard requires no update, since it never stored the key, only the subscription ID.
5. **Unknown-subscription flow**: telemetry arrives with a subscription ID not present in `MemberSubscription` → record is stored with `member_id = null` → surfaced only in the admin-only reconciliation view, never auto-assigned.

---

## 4. Data-model plan

Entities, fields, and the "never store" list are already fully specified in the project brief (Section 10) — this plan adopts them as-is with the following additions:

**Indexes / constraints**
- Unique index on `MemberSubscription.apim_subscription_id`.
- Unique index on `(organization_id, slug)`, `(department_id, slug)`, `(department_id, name)` for teams.
- Composite index on `UsageEvent(member_id, timestamp)` and `UsageEvent(team_id, timestamp)` for the two most common dashboard queries.
- Unique constraint preventing two *active* `BudgetPolicy` rows for the same `(scope_type, scope_id)` at overlapping `effective_from`/`effective_to` ranges.

**Migration approach**: Alembic, one migration per phase (not squashed), so Neal can inspect schema history independently.

**Historical team membership**: `UsageEvent` stores `team_id` and `department_id` as they were *at request time* (denormalized), not derived live from the member's current team — so a member moving teams doesn't rewrite history.

**Soft deletion**: `Organization`, `Department`, `Team`, `Member` use a `status` field (`active` / `inactive` / `archived`) rather than hard deletes, so historical `UsageEvent` foreign keys remain valid.

**Retention**: no automatic deletion in the MVP; document a manual retention policy in `docs/security.md` for later.

**PII / secret handling**: `Member.email` is the only PII field; it is never used as a metric dimension or logged. No table stores raw APIM keys, Azure credentials, or request/response content, per the brief's explicit prohibition.

---

## 5. API contract plan

All endpoints versioned under `/api/v1`. Every endpoint requires a resolved role and enforces scope server-side (frontend visibility is not authorization). Full request/response schemas live in `backend/app/schemas/`; this table summarizes contract shape.

| Resource | Endpoints | Required role (minimum) | Notes |
|---|---|---|---|
| Auth | `POST /auth/dev-login`, `GET /auth/me`, `POST /auth/logout` | none / any | Dev-login must be hard-disabled when `AUTH_MODE != development` |
| Organizations | `GET/POST /organizations`, `GET/PATCH /organizations/{id}` | org admin for write, scoped read otherwise | |
| Departments | `GET/POST .../departments`, `GET/PATCH /departments/{id}` | dept manager+ | |
| Teams | `GET/POST .../teams`, `GET/PATCH /teams/{id}` | team manager+ | |
| Members | `GET/POST .../members`, `GET/PATCH /members/{id}` | team manager+ | |
| Subscription mapping | `GET/PUT /members/{id}/subscription`, `PATCH/DELETE /subscriptions/{id}` | org admin | Never returns raw keys |
| Usage | `GET /usage/{summary,timeseries,by-department,by-team,by-member,by-model,recent,errors,unmapped}` | scoped to caller's role | All accept `date_from`, `date_to`, `organization_id`, `department_id`, `team_id`, `member_id`, `model`, `status`, `interval`, `timezone`; all paginated except `summary` |
| Budgets | `GET/POST /budgets`, `PATCH /budgets/{id}`, `GET /budgets/status` | org admin for write | |
| Models | `GET/POST /models`, `PATCH /models/{id}` | org admin | |
| Alerts | `GET /alerts`, `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve` | team manager+ scoped | |
| Audit | `GET /audit-events` | org admin | |
| System | `GET /system/health`, `GET /system/configuration-status`, `GET /system/telemetry-status` | none / org admin for detail | `configuration-status` reports missing env var *names* only, never values |

Standard error shape: `{ "error": "<code>", "message": "<human readable>", "field_errors": [...] }`; standard pagination: `?page`, `?page_size`, response includes `total`, `page`, `page_size`.

---

## 6. Frontend plan

- **Routing**: role-aware route tree (`/org`, `/org/departments/:id`, `/.../teams/:id`, `/.../members/:id`, `/admin/*`), redirect to the highest-scoped page the caller's role permits.
- **Layouts**: shell with role-specific left nav; admin section visually separated.
- **Core pages**: Organization overview, Department, Team, Member, and the Administration pages listed in Section 15 of the brief — implemented as-is.
- **Shared components**: usage line/bar charts (Recharts), budget-utilization bars, filter bar (date range, org/dept/team/member/model/status, interval, timezone), paginated usage table, alert banner, unmapped-subscription table.
- **State/data**: TanStack Query for all server data, no client-side caching of anything security-sensitive beyond the session.
- **States to handle explicitly**: loading, empty, partial-telemetry (some dimensions missing), error, Azure-disconnected (`TELEMETRY_SOURCE=seed` banner shown when not using live data).
- **Accessibility**: keyboard-navigable charts/tables, ARIA labels on all interactive elements, color is never the only signal on budget-status indicators.

---

## 7. Telemetry plan

- **Interface**: the `TelemetryProvider` protocol from the brief (Section 9), implemented by `SeedTelemetryProvider` and `AzureMonitorTelemetryProvider`, selected once at startup via `TELEMETRY_SOURCE`.
- **KQL**: one `.kql` file per query under `infra/queries/`, each with a version comment at the top; the Azure provider loads and parametrizes these rather than building Kusto strings inline.
- **Normalization**: both providers return the same internal DTO shape; Azure-specific field names (whatever APIM/App Insights actually calls them — to be confirmed in Phase 9) are mapped to the internal `UsageEvent`-shaped DTO in `telemetry/normalizers.py`, isolated from the rest of the app.
- **Edge cases handled explicitly, not implicitly**: unknown subscription ID → reconciliation view, not silent drop; missing token counts → `null`, never coerced to `0`; duplicate events → deduplicated on `request_id`/`correlation_id` where available; delayed telemetry → dashboard shows a "data as of" timestamp rather than implying real-time completeness.
- **Cardinality**: aggregate metrics (org/team/model totals) are treated as always-available; per-member detail is treated as potentially incomplete at high member counts, with a documented fallback to event-log-based aggregation if the metric-dimension limit is hit (exact limit to confirm in Phase 9 against current docs).

---

## 8. Azure integration plan

- **APIM mapping**: one Product per team, one Subscription per member — exactly as specified in Section 4 of the brief.
- **Keys**: primary/secondary keys are both valid, both resolve to the same subscription ID, and the dashboard stores neither — only the subscription ID.
- **Unified Model API**: two backend formats per Section 2 of the earlier conversation — OpenAI Chat Completions API and Anthropic Messages API — configured with client-facing aliases.
- **Managed identity**: APIM's managed identity invokes the approved LLM backend; no static backend secrets stored in APIM policy XML where avoidable.
- **Policies**: `llm-token-limit` (rate + quota, keyed on `context.Subscription.Id`) and `llm-emit-token-metric` (dimensioned by subscription, product, backend, API ID) — exact attribute names and behavior must be verified against current docs before Phase 9, not assumed from the draft XML in the brief.
- **Bicep boundary**: this repo owns Bicep for the *policy attachment and unified model API configuration*; it does not own provisioning the APIM instance, the LLM backend resource, or the Application Insights resource itself — those are Neal's pre-existing resources per Section 5.
- **Required Azure roles for Neal**: APIM Service Contributor (or narrower custom role) on the APIM instance, Monitoring Reader on Application Insights, and whatever role grants the managed identity permission to invoke the LLM backend.
- **Preview risk**: the Unified Model API and possibly the token-limit/metric policies are preview features as of this plan; confirm GA status before treating any of this as production-stable.
- **Cost considerations**: APIM tier cost, Application Insights ingestion cost, and LLM token cost are all Neal's responsibility to monitor; this repo only estimates the last of the three.

---

## 9. Security plan

**Threat model** (condensed from the brief's Section 19 and the local gateway): stolen or shared subscription keys, member impersonation via forged headers, cross-team/department/org data leakage, broken object-level authorization, credentials committed to git or leaked via logs/frontend/Azure queries, accidental prompt/completion storage, SQL injection, filter-manipulation, rate-limit bypass, duplicate telemetry, metric-cardinality data loss, streaming token inaccuracy, dev-auth accidentally enabled in production, and unauthorized or unexpected billable calls to the configured third-party LLM provider. The local gateway introduces three additional facts that were not present in prior phases: `GATEWAY_LLM_API_KEY` is a real billable third-party credential and must never be logged, returned in a response, or exposed to the frontend; `Ocp-Apim-Subscription-Key` is a second authentication system entirely separate from Phase 5's cookie-session authentication, and the seeded subscription IDs are sequentially numbered and therefore guessable; and employee prompt content now genuinely leaves this system for the configured third-party LLM provider, whereas no prior phase sent prompt content outside the application.

**Non-negotiable rules**: no raw APIM keys ever stored or returned; no `GATEWAY_LLM_API_KEY`, session secret, or subscription-key header value sent to the browser or included in any success or error response; no Azure credentials sent to the browser; no subscription-key, authorization header, prompt, completion, or LLM credential logged; no prompts/completions stored by default beyond forwarding the prompt to the configured provider for a gateway request; no email addresses in metric dimensions; `DefaultAzureCredential` everywhere, managed identity preferred in Azure; every backend endpoint enforces authorization independent of frontend routing; every filter is validated against the caller's permitted scope server-side; every admin mutation, including alert acknowledgement and resolution, is audit-logged; dev-login fails closed (returns 404, not a login form) whenever `AUTH_MODE != development`.

---

## 10. Testing plan

- **Backend unit**: hierarchy logic, subscription mapping, unknown-subscription handling, budget inheritance resolution, token aggregation, cost calculation, timezone/date filtering, alert thresholds, role checks, telemetry normalization, missing/duplicate-token handling.
- **Backend integration**: per-role access matrix (org admin / dept manager / team manager / member), cross-scope access explicitly denied, seed provider output shape, mocked Azure provider output and failure handling, reconciliation view, pagination, no credentials ever present in a response body.
- **Local gateway**: authentication, provider failure handling, usage attribution, and budget enforcement are covered in `backend/tests/test_gateway.py`; the full review must additionally verify that gateway credentials and subscription headers never appear in success or error responses.
- **Frontend**: each dashboard page, chart rendering, budget indicators, filters, loading/empty/partial/error states, Azure-disconnected state, role-based navigation, accessibility checks.
- **End-to-end (seed data only)**: the 12-step flow from Section 24 of the brief, run against `TELEMETRY_SOURCE=seed`.
- **Azure smoke tests**: the 20 checks from Section 23 of the brief — separate script suite, never run in standard PR CI, requires Neal's real environment variables.
- **CI**: GitHub Actions runs backend/frontend lint, type-check, unit + integration + frontend tests, Docker build validation, Bicep/policy validation where practical, and a secret-scan — all without Azure credentials, per Section 25.

---

## 11. Phased implementation plan

### Local gateway addendum

Real Azure APIM access was lost mid-project, so a local `/gateway/v1` OpenAI-compatible
gateway was added to prove the unified-model-API flow end to end. It authenticates with
the existing member subscription mapping, forwards to an OpenAI-compatible provider, and
writes live usage directly to the existing usage-event table. Phase 8's Azure Monitor
provider remains unchanged and is still the intended production telemetry path when Azure
access returns.

| Phase | Goal | Key deliverables | Tests | Complexity |
|---|---|---|---|---|
| 0 | Repo foundation & tooling | `docker-compose.yml`, `.env.example`, backend/frontend skeletons, CI skeleton, one documented start command | CI runs green on an empty app | Small |
| 1 | Database schema & seed data | All models from Section 10 of the brief, Alembic migrations, `sample-data/*.json`, seed loader | Unit tests for schema constraints and seed loader | Medium |
| 2 | Telemetry-provider abstraction | `TelemetryProvider` interface, `SeedTelemetryProvider` fully implemented, `AzureMonitorTelemetryProvider` stubbed (not yet querying real Azure) | Unit tests against seed provider, interface conformance test | Medium |
| 3 | Org/member management APIs | Organizations/Departments/Teams/Members/Subscription-mapping endpoints | Integration tests for CRUD + authorization | Medium |
| 4 | Usage aggregation & budget APIs | `/usage/*` and `/budgets/*` endpoints reading from the seed provider | Unit tests for aggregation math and inheritance resolution | Large |
| 5 | Auth & role authorization | Dev-login, role model, per-endpoint scope enforcement | Full role-access-matrix integration tests | Medium |
| 6 | Dashboard frontend | All pages from Section 15 of the brief, wired to Phases 3–5's APIs | Frontend + accessibility tests | Large |
| 7 | Alerts, audit, reconciliation | Alert computation on refresh, audit log writes, unmapped-subscription view | Unit + integration tests for alert thresholds | Medium |
| 8 | Azure Monitor telemetry provider | Real KQL execution, DTO normalization, `DefaultAzureCredential` auth | Tests against mocked Azure responses | Large |
| 9 | Superseded by local-gateway budget enforcement | Azure access was lost mid-project, so local gateway enforcement replaced the planned APIM policies, KQL, and Bicep work. | Gateway budget enforcement tests | Medium |
| 10 | Superseded by local-gateway operations | Operational documentation for the local gateway is the practical replacement for the planned Azure handoff docs and smoke tests. | Local gateway verification | Small |
| 11 | End-to-end review & hardening | Full e2e pass, security review against Section 19's threat model, doc pass | Full test suite green, manual security checklist signed off | Medium |

Each phase should become one or more GitHub issues (Section 12) sized for a single Copilot Agent task rather than implemented as one giant PR.

---

## 12. GitHub issue backlog

Grouped by phase; each is independently implementable.

**Phase 0**
1. *Scaffold backend* — FastAPI app skeleton, `pyproject.toml`, Ruff config, Pytest config. Files: `backend/app/main.py`, `backend/pyproject.toml`. Acceptance: `uvicorn app.main:app` serves `/system/health`.
2. *Scaffold frontend* — Vite + React + TS + Tailwind, empty shell page. Files: `frontend/*`. Acceptance: `npm run dev` serves a blank shell.
3. *Docker Compose + one-command start* — Files: `docker-compose.yml`, `README.md` run section. Acceptance: `docker compose up` starts both services.
4. *CI skeleton* — Files: `.github/workflows/ci.yml`. Acceptance: green run on the empty scaffold.

**Phase 1**
5. *SQLAlchemy models + Alembic init* — all entities from Section 10. Acceptance: `alembic upgrade head` succeeds on a clean DB.
6. *Seed data fixtures* — `sample-data/*.json` meeting every requirement in Section 20 of the brief (30+ days, blocked/rate-limited/error events, unmapped subscription, etc.). Acceptance: seed loader populates DB without error.

**Phase 2**
7. *TelemetryProvider interface + Seed implementation* — Acceptance: seed provider satisfies interface conformance tests.
8. *Azure provider stub* — signature-complete, returns `NotImplementedError` bodies. Acceptance: app boots with `TELEMETRY_SOURCE=application_insights` without crashing, even though queries aren't live yet.

**Phase 3**
9. *Org/Department/Team/Member CRUD endpoints*
10. *Member-subscription mapping endpoints* (no raw key storage/return)

**Phase 4**
11. *Usage aggregation endpoints* (`summary`, `timeseries`, `by-*`)
12. *Budget CRUD + inheritance resolution + status endpoint*

**Phase 5**
13. *Role model + dev-login* (hard-fails outside dev)
14. *Per-endpoint authorization enforcement + access-matrix tests*

**Phase 6**
15. *Organization/Department/Team/Member dashboard pages*
16. *Admin pages* (orgs, models/prices, budgets, alerts, audit, unmapped subscriptions, Azure connection status)

**Phase 7**
17. *Alert computation + display*
18. *Audit log writes on every admin mutation*

**Phase 8**
19. *Real KQL execution + DTO normalization for Azure provider*

**Phase 9**
20. *Superseded: local-gateway budget enforcement replaced the planned APIM policy XML, Bicep, and KQL work after Azure access was lost mid-project.*

**Phase 10**
21. *Superseded: local-gateway operational documentation is the practical replacement for the planned Azure handoff docs and smoke-test scripts.*

**Phase 11**
25. *End-to-end test pass + security checklist sign-off*

---

## 13. Risk register

| Risk | Likelihood | Impact | Mitigation | Owner | Validation |
|---|---|---|---|---|---|
| APIM feature availability differs from what's documented | Medium | High | Verify tier/preview status before Phase 9, not during planning | Dashboard team | Manual doc check + Neal confirms his tier |
| Preview features change syntax before GA | Medium | Medium | Pin policy XML to a dated doc snapshot; re-verify before each Azure phase | Dashboard team | Diff against docs at Phase 9 start |
| Azure cost exposure (App Insights ingestion, APIM tier) | Low–Medium | Medium | Neal owns cost monitoring; dashboard never auto-provisions expensive resources | Neal | Cost alert on Neal's subscription |
| Token-count accuracy, especially streaming | Medium | Medium | `token_count_estimated` flag on records; never present estimates as exact | Dashboard team | Smoke test #12 |
| Metric-dimension cardinality limit | Medium | Medium | Aggregate/detail split designed in from Phase 2, not retrofitted | Dashboard team | Confirm exact limit at Phase 9 |
| Telemetry delay | High | Low | "Data as of" timestamp shown in UI, never implied real-time | Dashboard team | Manual QA |
| Missing telemetry fields | Medium | Medium | `null`, never `0`; explicit partial-data UI state | Dashboard team | Unit tests in Phase 2 |
| Key sharing between employees | Low | Medium | Documented in security plan; not technically preventable from this repo | Neal | Handoff doc note |
| Secret exposure in repo/logs/frontend | Low | High | Secret-scan in CI, no raw keys stored anywhere, redacted smoke-test output | Dashboard team | CI secret-scan + code review |
| Cross-team/department authorization bypass | Low | High | Full access-matrix integration tests in Phase 5 | Dashboard team | Phase 5 test suite |
| Model price changes mid-period | Medium | Low | Effective-dated `ModelConfiguration` rows | Dashboard team | Unit tests in Phase 4 |
| Local seed data diverging from real Azure data shape | Medium | Medium | Both providers implement the same interface and DTO; normalizer tested against sample real payloads at Phase 8 | Dashboard team | Phase 8 mocked-response tests |
| KQL schema differences from assumptions | Medium | Medium | KQL files versioned and re-verified against Neal's actual schema before Phase 9 sign-off | Dashboard team + Neal | Phase 9/10 |
| Unknown subscription IDs mis-attributed | Low | High | Never auto-assign; reconciliation view is mandatory, not optional | Dashboard team | Unit test in Phase 2 |

---

## 14. Final build order

**Recommended first issue: Phase 0, Issue #1–4 combined — "Repository scaffolding and developer tooling."**

Why first: it has zero dependencies, requires no business-logic decisions, and de-risks the development loop (one-command start, CI green) before any real feature work begins. Every later phase depends on it, and it's small enough to validate that Copilot Agent Mode, the CI pipeline, and the local dev workflow all work together before investing in the data model or telemetry logic.

**Copilot Agent implementation prompt for this issue** (scope this task to only what's below — do not implement Phase 1 or later in the same pass):

> Implement Phase 0 of `docs/implementation-plan.md`: repository scaffolding and developer tooling. Create a FastAPI backend skeleton at `backend/` (pyproject.toml with FastAPI, Uvicorn, Pydantic, Pytest, Ruff; `app/main.py` exposing `GET /api/v1/system/health` returning `{"status": "ok"}`). Create a React + TypeScript + Vite + Tailwind frontend skeleton at `frontend/` with a single placeholder landing page that fetches and displays the health-check response. Add a root `docker-compose.yml` that starts both services with one command. Add `.env.example` at the root with the variables listed in Section 21 of `docs/implementation-plan.md`, all unset. Add a `.gitignore` covering Python, Node, and a `secrets/` directory. Add `.github/workflows/ci.yml` that installs backend and frontend dependencies, runs Ruff and Pytest, runs frontend lint/type-check/build, and requires no Azure credentials or secrets. Update the root `README.md` with a single documented command to start the whole stack locally. Do not implement any database models, telemetry providers, or business endpoints beyond the health check — those are separate issues. When finished, confirm `docker compose up` serves the health check and the CI workflow passes on an empty diff.

---

*This document corresponds to Section 28 of the original planning brief. Sections 1–14 above map directly to items 1–14 requested there.*
