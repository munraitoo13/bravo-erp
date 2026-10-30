# `PLAN.md` — Living Execution Roadmap & Task Tracker

> **Current Session Handoff Notes:**
> - **Active Phase:** Phase 6: Post-Audit Hardening, Security & Production Readiness
> - **Completed in Current Turn:** Milestones 6.1, 6.2, 6.3 (Domain Invariants, RFC 7807 Catch-All & Zero-Ignore Typing), and 6.4 (UX & Recruiter Demo Polish) completed and verified across all Quality Gates (ruff check/format, mypy --strict, pytest Testcontainers, tsc, eslint, docker-compose config).
> - **Next Immediate Action:** Ready to proceed with Milestone 6.5 (Edge-Case Test Expansion & Production Deployment Assets).

---

## Legend
- `[ ]` **Pending:** Not yet started.
- `[~]` **In Progress:** Currently being implemented or verified.
- `[x]` **Completed:** Implemented and verified against the Phase Quality Gate.

---

## Phase 0: Governance Documentation, CLI Scaffolding & Container Watch Foundation

### Tasks
- [x] **0.1: Generate AI-First Governance Documentation**
  - Create `AGENTS.md` (Mandatory 4-step workflow loop, CLI-first rules, Python 3.12+/SQLAlchemy 2.0/RFC 7807 standards, Docker Compose Watch command matrix).
  - Create `SPEC.md` (Monorepo tree, Mermaid ERD for all 10 tables, JSONB `specs` schemas per category, CCTV Sizing Engine math & lookup tables, State Machines, `SELECT ... FOR UPDATE` algorithm, RBAC response redaction, API catalog).
  - Create `DECISIONS.md` (ADRs 001 through 007).
  - Create `PLAN.md` (this living roadmap).
- [x] **0.2: Root Configuration & Backend CLI Scaffolding (`uv` + `alembic`)**
  - Create `.agent/rules/governance.md`, `.gitignore`, `.env.example`, `.env`, and initial `README.md`.
  - Initialize backend via `uv init` and install runtime + dev dependencies via `uv add`.
  - Configure strict `ruff`, `mypy --strict`, and `pytest` settings in `backend/pyproject.toml`.
  - Initialize async Alembic environment via `uv run alembic init -t async migrations`.
- [x] **0.3: Frontend CLI Scaffolding (`pnpm` + `Next.js` + `shadcn/ui`)**
  - Scaffold Next.js App Router TypeScript project via `pnpm create next-app@latest`.
  - Initialize `shadcn/ui` and add primitive UI components via `pnpm dlx shadcn@latest`.
  - Install TanStack Query, React Hook Form, Zod, and Lucide icons via `pnpm add`.
  - Enforce `noUncheckedIndexedAccess: true` in `frontend/tsconfig.json`.
- [x] **0.4: Dockerfiles & CachyOS Hybrid `docker-compose.dev.yml`**
  - Create `backend/Dockerfile.dev` (Python 3.12 + `uv` + WeasyPrint system shared libraries: Pango, Cairo, GDK-PixBuf).
  - Create `frontend/Dockerfile.dev` (Node LTS + `pnpm`).
  - Create `docker-compose.dev.yml` with `postgres:17-alpine`, `redis:7-alpine`, `minio/minio`, `minio-setup` (`mc mb`), `backend`, `worker`, and `frontend` with healthchecks, Linux bind mounts for `src/`, anonymous volumes for `.venv`/`node_modules`, and `develop.watch` rebuild triggers.
- [x] **0.5: Minimal Healthcheck Entrypoints & Container Boot Verification**
  - Wire `backend/src/core/` (`config.py`, `logging.py`, `exceptions.py`, `database.py`, `broker.py`), `backend/src/main.py` (`/api/v1/health`), `backend/src/worker.py`, and smoke tests in `backend/tests/test_health.py`.

### CLI Scaffolding Commands to Run (Phase 0)
```bash
# Backend CLI initialization & dependencies
uv init --app --python 3.12 backend
uv add --project backend fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic pydantic pydantic-settings "pydantic[email]" taskiq taskiq-redis taskiq-fastapi redis structlog pyjwt "pwdlib[argon2]" weasyprint "qrcode[pil]" jinja2 aioboto3 httpx python-multipart
uv add --project backend --dev pytest pytest-asyncio pytest-cov "testcontainers[postgres,redis]" ruff mypy aiosqlite

# Async Alembic initialization
uv run --project backend alembic init -t async backend/migrations

# Frontend CLI initialization & dependencies
pnpm create next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-pnpm --yes
pnpm --dir frontend dlx shadcn@latest init -d -y
pnpm --dir frontend dlx shadcn@latest add button card input label select table badge dialog tabs form sonner dropdown-menu separator sheet skeleton alert -y
pnpm --dir frontend add @tanstack/react-query react-hook-form zod @hookform/resolvers lucide-react clsx tailwind-merge
```

### Phase 0 Verification Gate
```bash
uv run --project backend ruff check backend/src
uv run --project backend mypy --config-file backend/pyproject.toml backend/src --strict
pnpm --dir frontend tsc --noEmit
docker compose -f docker-compose.dev.yml config --quiet
docker compose -f docker-compose.dev.yml up --build -d
docker compose -f docker-compose.dev.yml ps
```

---

## Phase 1: Core Infrastructure, Database Schema, Multi-Tenancy, Catalog & 1-Click Recruiter Demo

### Tasks
- [x] **1.1: Core Infrastructure (`backend/src/core/`)**
  - Implement `config.py` (`Settings` via `pydantic-settings`).
  - Implement `database.py` (`AsyncEngine`, `async_sessionmaker`, `Base`, `UUIDv7` generator).
  - Implement `logging.py` (`structlog` JSON processor + `CorrelationIdMiddleware` propagating `X-Correlation-ID`).
  - Implement `exceptions.py` (`DomainError` hierarchy + global RFC 7807 `application/problem+json` exception handlers).
  - Implement `security.py` (Argon2id password hashing via `pwdlib` + JWT access token encode/decode).
  - Implement `dependencies.py` (`CurrentTenantContext`, `get_current_tenant_context`, `require_role`).
  - Implement `storage.py` (Async S3/MinIO client for bucket uploads and presigned URL generation).
- [x] **1.2: Complete ORM Models & Initial Alembic Migration**
  - Implement ORM models for all 10 tables specified in `SPEC.md`: `organizations`, `users`, `catalog_items`, `customers`, `quotes`, `quote_items`, `work_orders`, `installed_serials`, `audit_logs`, `outbox_events`.
  - Wire all model metadata into `backend/alembic/env.py`.
  - Generate and apply the initial Alembic migration via CLI inside the `backend` container.
- [x] **1.3: Multi-Tenancy, Auth & 1-Click Recruiter Demo (`backend/src/modules/tenants/`)**
  - Implement `tenants/schemas.py`, `tenants/repository.py`, `tenants/service.py`, and `tenants/router.py`.
  - Expose `POST /api/v1/auth/login`, `POST /api/v1/auth/demo-login` (`OWNER`, `TECHNICIAN`, `PUBLIC_CLIENT`), `POST /api/v1/auth/demo-reset`, and `GET /api/v1/auth/me`.
- [x] **1.4: Equipment Catalog Module & Role-Segregated Schemas (`backend/src/modules/catalog/`)**
  - Implement category-discriminated Pydantic v2 schemas (`DvrSpecs`, `AnalogCameraSpecs`, `IpCameraSpecs`, `HddSpecs`, `PowerSupplySpecs`, `PoeSwitchSpecs`, `CableSpecs`, `GenericAccessorySpecs`).
  - Implement `CatalogItemOwnerResponse` (includes `cost_price_cents`) vs `CatalogItemTechnicianResponse` (omits `cost_price_cents`).
  - Implement `catalog/repository.py`, `catalog/service.py` (enforcing `DemoProtectionError` on deleting `is_seed_protected` items), and `catalog/router.py`.
- [x] **1.5: Idempotent PT-BR Demo Seeder (`backend/src/seed/demo_seeder.py`)**
  - Populate Demo Tenant (`"Bravo Segurança Eletrônica Ltda"`), Demo `OWNER` & `TECHNICIAN` users, full Intelbras/WD Purple/MCM/Condutti/Furukawa PT-BR catalog, and the 3 pre-seeded Demo Quotes & Work Orders.
- [x] **1.6: Phase 1 Unit & Integration Tests**
  - Write `tests/unit/test_rbac_schemas.py` verifying zero leakage of `cost_price_cents` or `margin_percent` in Technician/Public schemas.
  - Write `tests/integration/test_tenant_isolation.py` verifying cross-tenant queries return `404` and `is_seed_protected` items return `403 Problem+JSON` on delete.

### CLI Commands to Run (Phase 1)
```bash
docker compose -f docker-compose.dev.yml exec backend uv run alembic revision --autogenerate -m "initial_bravo_erp_schema"
docker compose -f docker-compose.dev.yml exec backend uv run alembic upgrade head
docker compose -f docker-compose.dev.yml exec backend uv run python -m src.seed.demo_seeder
```

### Phase 1 Verification Gate
```bash
uv run --project backend ruff check backend/src backend/tests
uv run --project backend ruff format --check backend/src backend/tests
uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests --strict
uv run --project backend pytest backend/tests/unit/test_rbac_schemas.py backend/tests/integration/test_tenant_isolation.py -v
```

---

## Phase 2: Pure Domain CCTV Engineering & Sizing Engine (`sizing`)

### Tasks
- [x] **2.1: Pure Domain Value Objects & Bitrate Lookup Table (`backend/src/modules/sizing/domain/`)**
  - Implement `value_objects.py` and `bitrate_table.py` covering `720p`, `1080p`, `4MP`, `4K` across `15`, `20`, `30` FPS and `H.264`, `H.265`, `H.265+` Smart Codec.
- [x] **2.2: Storage, Intelbras MHDX Hybrid Topology & Electrical Strategies**
  - Implement `StorageCalculationStrategy`: daily GB formula, 15% safety margin, and optimal WD Purple HDD combination selector respecting `max_sata_slots` and `max_tb_per_slot`.
  - Implement `MHDXHybridTopologyStrategy`: validates `native_bnc_channels`, `extra_ip_channels`, BNC-to-IP channel conversion, incoming bandwidth Mbps, and pure IP NVR selection.
  - Implement `ElectricalAndBomStrategy`: $1.30\times$ IR-on current draw, 12V switching PSU / PoE switch budget selection, copper cable voltage drop ($\Delta V = 2 \times L \times I \times R_{\text{meter}}$) with `< 10.8V` warning flag, and deterministic derivation of baluns, P4/BNC/RJ45 connectors, junction boxes, cable rolls (`1.15x` slack), and labor points.
- [x] **2.3: Sizing Service & FastAPI Endpoint (`/api/v1/sizing/calculate`)**
  - Implement `sizing/schemas.py`, `sizing/service.py` (matches pure domain calculation against the tenant's active `catalog_items`), and `sizing/router.py`.
- [x] **2.4: 100% Unit Test Coverage for Sizing Engine**
  - Write `tests/unit/test_sizing_engine.py` testing exact mathematical outputs, MHDX 4/8/16/32ch hybrid conversions, multi-SATA HDD upgrades, voltage drop warnings over long cable runs, and BOM item counts.

### Phase 2 Verification Gate
```bash
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests --strict
uv run --project backend pytest backend/tests/unit/test_sizing_engine.py --cov=src.modules.sizing.domain --cov-fail-under=100 -v
```

---

## Phase 3: Quotes, State Machine, Pessimistic Locking & Transactional Outbox (`quotes`)

### Tasks
- [x] **3.1: Quote State Machine & Audit Diff Builder (`backend/src/modules/quotes/state_machine.py`)**
  - Implement `QuoteStateMachine` enforcing valid transitions (`DRAFT -> SENT -> APPROVED -> IN_PROGRESS -> COMPLETED`, `CANCELED`, `EXPIRED`) and generating structured `previous_state`/`new_state` dicts for `audit_logs`.
- [x] **3.2: Quote & Customer Repositories and Role-Aware Schemas**
  - Implement `QuoteOwnerResponse`, `QuoteTechnicianResponse`, and `QuotePublicResponse` in `quotes/schemas.py`.
  - Implement `quotes/repository.py` including deterministic ascending-UUID `SELECT ... FOR UPDATE` catalog locking (`lock_catalog_items_for_update`).
- [x] **3.3: Atomic Quote Approval Unit of Work & Transactional Outbox Emission**
  - Implement `quotes/service.py`:
    - Create quote (from manual items or sizing engine snapshot).
    - Send quote (`DRAFT -> SENT` + `QuoteSentEvent` in `outbox_events`).
    - Public/Owner approve quote (`SENT -> APPROVED` + `SELECT ... FOR UPDATE` stock reservation + `WorkOrder` creation with default PT-BR checklist + `AuditLog` + `QuoteApprovedEvent` in `outbox_events`).
    - Cancel quote (releases `reserved_quantity` if `APPROVED`).
  - Expose `/api/v1/customers/*`, `/api/v1/quotes/*`, and `/api/v1/public/quotes/{public_token}/*` in `quotes/router.py`.
- [x] **3.4: State Machine Unit Tests & Parallel Concurrency Integration Test**
  - Write `tests/unit/test_state_machines.py`.
  - Write `tests/integration/test_quote_concurrency.py` using `asyncio.gather` to fire concurrent approval requests for two quotes competing for the last `1` unit of an `Intelbras MHDX 1108` DVR in stock—proving one returns `200 OK`, the second returns `409 Conflict` (`application/problem+json`), and `reserved_quantity` equals `1`.

### Phase 3 Verification Gate
```bash
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests --strict
uv run --project backend pytest backend/tests/unit/test_state_machines.py backend/tests/integration/test_quote_concurrency.py -v
```

---

## Phase 4: Field Work Orders, Serial Number Vault, Warranty Engine & Async PDF Worker (`work_orders` & `tasks`)

### Tasks
- [x] **4.1: Work Order Execution & Serial Number Vault (`backend/src/modules/work_orders/`)**
  - Implement `work_orders/state_machine.py`, `work_orders/schemas.py`, `work_orders/repository.py`, `work_orders/service.py`, and `work_orders/router.py`.
  - Implement checklist toggling, MinIO photo upload (`POST /api/v1/work-orders/{id}/photos`), and hardware Serial Number registration (`POST /api/v1/work-orders/{id}/serials` with automatic computation of `distributor_warranty_until` and `client_warranty_until`).
  - Implement strict completion guards on `POST /api/v1/work-orders/{id}/complete` (all checklist steps checked, $\ge 1$ photo, all serialize-mandatory hardware units registered in `installed_serials`), deducting physical `stock_quantity` and `reserved_quantity`, setting `warranty_expires_at = today + 365 days`, and emitting `WorkOrderCompletedEvent`.
- [x] **4.2: WeasyPrint PDF Proposal & Warranty Certificate Worker (`backend/src/modules/tasks/pdf_generator.py`)**
  - Create professional PT-BR Jinja2 HTML/CSS template (`templates/proposal_and_warranty.html`) rendering company header, customer info, technical sizing summary, itemized BOM (without cost/margin), acceptance metadata (IP + timestamp), installed hardware Serial Numbers & warranty table, and embedded verification QR Code image (Base64 PNG).
  - Render PDF bytes via WeasyPrint, compute hex `sha256`, upload PDF to MinIO (`proposals/{org_id}/{quote_id}.pdf`), and store `pdf_storage_key` + `pdf_sha256_hash` on `Quote`.
- [x] **4.3: Outbox Relay, 11-Month Warranty Cron & Public SHA-256 Verifier**
  - Implement `tasks/outbox_relay.py` (`SELECT ... FOR UPDATE SKIP LOCKED` on `outbox_events`).
  - Implement `tasks/warranty_cron.py` scanning `work_orders` where `warranty_expires_at <= current_date + 30 days` and `preventive_maintenance_alert_sent == False`, setting the flag and emitting `WarrantyExpiringAlertEvent`.
  - Implement `tasks/demo_reset_cron.py` for periodic Demo Tenant state restoration.
  - Expose `GET /api/v1/warranties/expiring` and `GET /api/v1/verify/{pdf_sha256_hash}`.
- [x] **4.4: Outbox, PDF Generation & Warranty Integration Tests**
  - Write `tests/integration/test_outbox_and_pdf.py` verifying the end-to-end flow: Quote Approval -> Work Order Serial Registration & Completion -> Outbox Relay -> WeasyPrint PDF rendered -> SHA-256 hash verified via `GET /api/v1/verify/{pdf_sha256_hash}`.

### Phase 4 Verification Gate
```bash
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests --strict
uv run --project backend pytest backend/tests -v
```

---

## Phase 5: Frontend Application (Next.js App Router, PT-BR UI, Strict TypeScript)

### Tasks
- [x] **5.1: Typed API Client, RFC 7807 Error Parser & Auth/Demo Context (`frontend/src/lib/`)**
  - Implement `api-client.ts` with `X-Correlation-ID` generation, JWT header injection, and RFC 7807 `application/problem+json` error parsing.
  - Implement `auth-context.tsx` supporting instant 1-Click Recruiter Demo persona switching (`Proprietário (Owner)`, `Técnico de Campo`, `Link Público do Cliente`) and `"Restaurar Dados da Demo"`.
  - Build `/login` page with prominent 1-Click Recruiter Demo cards alongside standard login.
- [x] **5.2: Executive Dashboard & 11-Month Warranty Radar (`/dashboard`)**
  - Build role-aware dashboard shell (`(dashboard)/layout.tsx`) with top Demo Persona Switcher banner.
  - Render financial KPIs (Total Quoted, Approved Revenue, Average Margin — visible only to `OWNER`), active Work Orders, and the **Radar de Renovação de Garantia (11 Meses)** card.
- [x] **5.3: Interactive CCTV Sizing Wizard (`/sizing`), Proposal Builder (`/quotes/new`) & Catalog Manager (`/catalog`)**
  - Build `/sizing` and `/quotes/new` interactive calculator & proposal builder: multi-group camera builder (Analog/IP, Resolution, FPS, Codec, Retention Days, Cable Type & Meters), live calculation of Required HDD TB, Intelbras MHDX hybrid channel utilization bar, 12V/PoE electrical load, voltage drop alerts, auto-derived BOM table, and 1-click `"Criar Orçamento a partir do Dimensionamento"`.
  - Build `/catalog` table displaying Intelbras/WD Purple/Condutti SKUs, physical vs. reserved stock badges, and cost/margin columns conditionally rendered for `OWNER`.
- [x] **5.4: Quotes Management (`/quotes`), Public Proposal Portal (`/p/[token]` & `/public/quotes/[token]`) & SHA-256 Verifier (`/verify/[hash]` & `/public/verify/[sha256]`)**
  - Build `/quotes` list, `/quotes/[id]` detail view, and `/quotes/new` proposal builder with state transition actions (`Enviar ao Cliente`, `Aprovar`, `Cancelar`), audit log timeline, and direct link to the public client portal.
  - Build `/p/[token]` and `/public/quotes/[token]` (zero-login client view) displaying the PT-BR commercial proposal, PDF download button, and 1-Click `"Aprovar Proposta Comercial"` button handling `409 Conflict` stock errors gracefully.
  - Build `/verify/[hash]` and `/public/verify/[sha256]` displaying cryptographic authenticity confirmation, SHA-256 digest, customer, approval IP/timestamp, and registered hardware serial warranties.
- [x] **5.5: Mobile-First Technician Work Order (`/work-orders/[id]`) & Equipment Warranty Vault (`/vault`)**
  - Build `/work-orders` list and `/work-orders/[id]` field execution screen:
    - Interactive checklist toggles (`checklist_json`).
    - Intelbras Cloud P2P ID input and installation photo upload (`POST /photos`).
    - **Cofre de Números de Série (Serial Vault):** form with S/N scanner/input to register DVR, WD Purple HDD, and Camera Serial Numbers mapped to channels (`BNC-01`, `SATA-01`, etc.).
    - `"Concluir Ordem de Serviço"` button enforcing all guards before transitioning to `COMPLETED`.
  - Build `/vault` Warranty & Equipment Serial Vault view listing all registered hardware serials across work orders, distributor vs. client warranty dates, 11-month maintenance radar, and 1-click SHA-256 certificate verification links.
- [x] **5.6: Final End-to-End Quality Gate & Documentation Polish**
  - Run full backend + frontend linters, strict typecheckers, unit/integration test suites, and production Next.js build verification.
  - Update `PLAN.md` all checkboxes to `[x]` and finalize `README.md`.

### Phase 5 Verification Gate (Final Definition of Done)
```bash
uv run --project backend ruff check backend/src backend/tests
uv run --project backend ruff format --check backend/src backend/tests
uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests --strict
uv run --project backend pytest backend/tests -v
pnpm --dir frontend tsc --noEmit
pnpm --dir frontend lint
pnpm --dir frontend build
```

---

## Phase 6: Post-Audit Hardening, Security & Production Readiness

### Tasks
- [x] **6.1: Governance Documentation & Living Architecture Sync**
  - Document S3 storage key prefix validation rule (`photos/{org_id}/{work_order_id}/`), upload size limits (10 MB), and MIME allowlist in `SPEC.md`.
  - Document cross-entity cancellation invariant (canceling an `APPROVED` quote cascades cancellation to child `WorkOrder`) in `SPEC.md`.
  - Fix documentation drift: reconcile `migrations/` paths and `UserRole.PUBLIC_CLIENT` in `SPEC.md`.
  - Update `DECISIONS.md` (ADR-005) with hybrid immediate `.kiq()` trigger + `taskiq scheduler` fallback and per-event savepoint isolation (`session.begin_nested()`).
- [x] **6.2: Remediate All P0 Vulnerabilities & Demo Blockers**
  - [x] **P0-1:** Fix standard login form in `frontend/src/app/(auth)/login/page.tsx` default values, placeholders, and hint box credentials to match `demo_seeder.py` (`carlos.mendes@bravoseguranca.com.br`, `rafael.silva@bravoseguranca.com.br`, `BravoDemo@2026`, `bravo-seguranca-demo`).
  - [x] **P0-2:** Harden photo upload and prevent S3 cross-tenant traversal in `WorkOrderService.upload_installation_photo` and `work_orders/router.py`. Reject supplied `photo_key` not prefixed with `photos/{ctx.organization_id}/{work_order.id}/` or containing `..`. Restrict uploads to `image/jpeg`, `image/png`, `image/webp` with 10 MB limit.
  - [x] **P0-3:** Add `scheduler` container to `docker-compose.dev.yml` running `uv run taskiq scheduler src.worker:scheduler`. Trigger `await poll_outbox_events_task.kiq()` immediately after successful database commits in `QuoteService` (`send_quote`, `_execute_atomic_approval`) and `WorkOrderService` (`complete_work_order`).
  - [x] **P0-4:** Harden Outbox Relay against S3 failures in `outbox_relay.py`: wrap each event in atomic savepoint (`async with session.begin_nested():`), broaden exception handler to capture all base exceptions (including botocore exceptions), increment `retry_count`, apply exponential `next_retry_at`, and recover stale `PROCESSING` events.
  - [x] **P0-5:** Seed real MinIO assets in demo tenant (`demo_seeder.py`): generate and upload real WeasyPrint PDF payloads for Quote #1 and Quote #3, and seed valid sample JPEG bytes for Work Orders #2 and #3 when storage is reachable.
- [x] **6.3: Domain Invariants, RFC 7807 Catch-All & Zero-Ignore Typing (P1)**
  - Cascade WorkOrder cancellation when an `APPROVED` quote is canceled; block WorkOrder execution on canceled quotes.
  - Require `WorkOrderStatus.IN_FIELD` for field execution and validate that registered serials match quote hardware.
  - Expose `POST /api/v1/quotes/{id}/revise` endpoint matching `QuoteStateMachine`.
  - Register global RFC 7807 catch-all exception handler for Starlette `HTTPException` and unhandled exceptions.
  - Eliminate `# type: ignore` comments in schemas and cache Argon2id password hash in `demo_seeder.py`.
- [x] **6.4: UX & Recruiter Demo Polish (P2)**
  - Render clickable preview links for `installation_photo_urls` in `work-orders/[id]/page.tsx`.
  - Add 1-Click Persona Switcher controls to `PublicQuotePortal` with seamless persona hand-off.
  - Fix `"Valor Venta"` typo to `"Valor de Venda:"` in `dashboard/page.tsx`.
  - Eliminate N+1 S3 client instantiation in list endpoints.
- [ ] **6.5: Edge-Case Test Expansion & Production Deployment Assets**
  - Add integration tests for S3 path validation, outbox relay S3 failure/retry, and cross-entity cancellation.
  - Add GitHub Actions CI workflow (`.github/workflows/ci.yml`).

### Phase 6 Verification Gate
```bash
uv run --project backend ruff check backend/src backend/tests
uv run --project backend ruff format --check backend/src backend/tests
uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests --strict
uv run --project backend pytest backend/tests -v
pnpm --dir frontend tsc --noEmit
pnpm --dir frontend lint
docker compose -f docker-compose.dev.yml config
```
