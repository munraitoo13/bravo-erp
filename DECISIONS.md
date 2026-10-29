# `DECISIONS.md` — Architecture Decision Records (ADRs)

> **Document Purpose:** Formal log of key architectural choices, engineering trade-offs, and constraints governing `bravo-erp`. Whenever an architectural decision is added or revised, a new ADR entry MUST be recorded here before modifying implementation code.

---

## ADR-001: Modular Monolith Architecture over Microservices

- **Status:** Accepted (2026-10-29)
- **Context:**
  `bravo-erp` spans five tightly cohesive domain sub-contexts: Multi-Tenancy & Auth (`tenants`), Equipment Catalog & Stock (`catalog`), CCTV Engineering & Sizing (`sizing`), Commercial Proposals (`quotes`), and Field Execution & Serial Tracking (`work_orders`). A critical business invariant requires that approving a quote atomically locks inventory rows, transitions the quote state, creates a field work order, writes an immutable audit log, and enqueues an outbox event within a single ACID transaction.
- **Decision:**
  Architect the backend as a **Modular Monolith** inside a single deployable FastAPI service (`backend/src/modules/{tenants,catalog,sizing,quotes,work_orders,tasks}`), enforcing strict module boundaries where cross-module mutations occur either through explicit application service orchestration sharing a single SQLAlchemy `AsyncSession` Unit of Work or asynchronously via `outbox_events`.
- **Consequences & Trade-offs:**
  - **Pros:**
    - Preserves local PostgreSQL ACID transactions (`SELECT ... FOR UPDATE`) across `quotes`, `catalog_items`, `work_orders`, `audit_logs`, and `outbox_events` without distributed 2-Phase Commit (2PC) or complex Saga compensating transactions.
    - Zero network serialization latency between the `sizing` engine and the `catalog` SKU matcher.
    - Dramatically simpler local development and recruiter evaluation (`docker compose -f docker-compose.dev.yml up`).
  - **Cons:**
    - Requires discipline to prevent spaghetti imports across modules. Enforced by keeping `sizing/domain/` 100% pure Python (zero ORM imports) and restricting cross-module write operations to the Service layer.

---

## ADR-002: Application-Level Multi-Tenancy via Explicit `organization_id` & FastAPI `CurrentTenantContext` Dependency Injection over PostgreSQL RLS

- **Status:** Accepted (2026-10-29)
- **Context:**
  As a multi-tenant B2B SaaS, `bravo-erp` must guarantee that Tenant A can never read or mutate Tenant B's catalog, quotes, customers, or serial numbers. Two primary patterns exist on PostgreSQL:
  1. Database-level Row-Level Security (RLS) policies relying on `SET LOCAL app.current_tenant_id = '...'` per connection checkout.
  2. Explicit application-level `organization_id` filtering enforced via a mandatory `CurrentTenantContext` object injected by FastAPI into every service and repository method.
- **Decision:**
  Use **explicit application-level `organization_id` filtering** enforced via FastAPI Dependency Injection (`CurrentTenantContext`) and composite B-Tree indexes prefixed with `organization_id` on all 10 tables.
- **Consequences & Trade-offs:**
  - **Pros:**
    - **Explicit & Auditable:** Every SQLAlchemy 2.0 `select()`, `update()`, and `delete()` query visibly includes `.where(Model.organization_id == ctx.organization_id)`, making query plans and composite index utilization transparent during code review and `EXPLAIN ANALYZE`.
    - **Connection Pool & Async Worker Safety:** Works seamlessly with PgBouncer transaction pooling, SQLAlchemy `AsyncSession`, and Taskiq background workers without risking session-variable bleed across pooled async connections.
    - **Public Token & Cross-Context Flows:** Supports token-scoped public routes (`/api/v1/public/quotes/{public_token}`) and system-wide Taskiq outbox polling cleanly without constantly toggling database superuser/RLS bypass roles.
  - **Cons:**
    - A developer forgetting `.where(Model.organization_id == ...)` in a raw query could risk a data leak. Mitigated by centralizing query construction in `TenantRepository` base helpers and running dedicated cross-tenant isolation integration tests (`tests/integration/test_tenant_isolation.py`).

---

## ADR-003: Taskiq (`taskiq-redis`) over Celery for Native `asyncio` Compatibility with FastAPI and SQLAlchemy 2.0

- **Status:** Accepted (2026-10-29)
- **Context:**
  The backend stack is 100% `async`/`await` (FastAPI, SQLAlchemy 2.0 `AsyncEngine`/`AsyncSession`, `aioboto3`/async MinIO client). Background workers must process the transactional outbox, render WeasyPrint PDFs, upload artifacts to MinIO, and execute scheduled cron jobs (11-month warranty expiration radar and periodic Demo Tenant reset).
  Celery 5.x was designed around synchronous WSGI architectures; running SQLAlchemy 2.0 `AsyncSession` inside Celery tasks requires fragile `asyncio.run()` or event-loop bridging per task, which breaks connection pool reuse across task executions.
- **Decision:**
  Adopt **Taskiq** (`taskiq`, `taskiq-redis`, `taskiq-fastapi`) backed by Redis 7+ as our distributed async task queue and cron scheduler.
- **Consequences & Trade-offs:**
  - **Pros:**
    - **Native `asyncio` Event Loop:** Taskiq workers run a persistent `asyncio` event loop and share the exact same FastAPI lifespan dependencies (`AsyncSession`, `structlog` context, async S3/MinIO client) via `taskiq_fastapi.init(broker, "src.main:app")`.
    - **Strict Typing:** First-class PEP 484/695 type hints on `@broker.task` decorators, passing `mypy --strict` without workarounds.
    - **Built-in Cron Scheduling:** Native `LabelScheduleSource` supports cron expressions for our 11-month preventive maintenance scanner and Demo Tenant reset jobs.
  - **Cons:**
    - Smaller ecosystem than legacy Celery (e.g., no Flower UI out of the box), which is fully offset by our structured JSON logging (`structlog` + `correlation_id`) and database-backed `outbox_events` observability table.

---

## ADR-004: Pessimistic Locking (`SELECT ... FOR UPDATE` with Deterministic UUID Ordering) for Inventory Reservation on Quote Approval

- **Status:** Accepted (2026-10-29)
- **Context:**
  In field operations, an installation company may have multiple open `SENT` quotes referencing the same scarce hardware in stock (e.g., the last unit of an `Intelbras MHDX 3116` DVR or `WD Purple 8TB` HDD). If two customers click "Approve Proposal" simultaneously via their public links, a naive read-then-write check (`if item.stock_quantity - item.reserved_quantity >= qty`) suffers from a classic **TOCTOU (Time-of-Check to Time-of-Use) race condition**, resulting in negative available inventory and over-promised installations.
- **Decision:**
  Enforce **Pessimistic Row-Level Locking** (`SELECT ... FOR UPDATE`) inside an atomic Unit of Work during quote approval, sorting all target `catalog_item_id` UUIDs in strict ascending order before issuing the lock query:
  ```python
  sorted_ids = sorted({line.catalog_item_id for line in physical_quote_items})
  stmt = (
      select(CatalogItem)
      .where(
          CatalogItem.organization_id == quote.organization_id,
          CatalogItem.id.in_(sorted_ids),
      )
      .order_by(CatalogItem.id.asc())
      .with_for_update()
  )
  ```
- **Consequences & Trade-offs:**
  - **Pros:**
    - **Mathematical Race-Condition Prevention:** PostgreSQL serializes concurrent transactions attempting to reserve overlapping SKUs. The second concurrent transaction waits until the first commits, immediately sees the updated `reserved_quantity`, and fails cleanly with an **RFC 7807 `409 Conflict`** (`InsufficientStockError`).
    - **Deadlock Immunity:** Sorting `catalog_item_id`s in ascending order guarantees that any two concurrent transactions locking overlapping subsets of items acquire row locks in the exact same topological order, making cyclic lock waits (deadlocks) impossible.
    - **Database Safety Net:** Backed by a PostgreSQL `CHECK (stock_quantity - reserved_quantity >= 0)` constraint on `catalog_items`.
  - **Cons:**
    - Holds row locks for the duration of the approval transaction (~2–5 ms). Because WeasyPrint PDF rendering and MinIO uploads are decoupled via the Transactional Outbox (ADR-005), zero network or CPU-heavy I/O occurs while the row locks are held.
  - **Implementation Nuance (SQLAlchemy Identity Map & `populate_existing=True`):**
    - Because `Quote.items` eagerly loads `QuoteItem.catalog_item` (`selectinload`) into the `AsyncSession` identity map when loading the `Quote`, a subsequent `select(CatalogItem).with_for_update()` query in the same session would normally return the already-cached Python `CatalogItem` instance without overwriting its attributes with the post-lock database values. All `SELECT ... FOR UPDATE` queries therefore chain `.execution_options(populate_existing=True)` so that when a blocked transaction acquires the row lock after a peer transaction commits, SQLAlchemy refreshes `stock_quantity` and `reserved_quantity` in-place from the locked database row.

---

## ADR-005: Transactional Outbox Pattern (`outbox_events`) for Reliable Async Side Effects (PDF Generation & Work Order Notifications)

- **Status:** Accepted (2026-10-29)
- **Context:**
  When a quote transitions to `SENT`, `APPROVED`, or `COMPLETED`, the system must generate a cryptographic WeasyPrint PDF proposal/warranty certificate and upload it to MinIO. Calling `await generate_pdf_task.kiq(...)` directly inside the HTTP request handler after `await session.commit()` introduces the **Dual-Write Problem**:
  - If Redis is transiently unreachable after the PostgreSQL commit, the quote is marked `APPROVED` in the database, but the PDF generation task is permanently lost.
  - Conversely, publishing to Redis *before* `await session.commit()` can cause the fast Taskiq worker to query PostgreSQL before the transaction commits, reading stale state.
- **Decision:**
  Implement the **Transactional Outbox Pattern** via the `outbox_events` PostgreSQL table. Domain services insert an `OutboxEvent(status="PENDING")` row inside the **exact same SQLAlchemy transaction** as the domain state mutation (`Quote`, `CatalogItem`, `WorkOrder`, `AuditLog`). A Taskiq relay worker polls `outbox_events` using `SELECT ... FOR UPDATE SKIP LOCKED`, dispatches the handler (`pdf_generator.py`), and marks the event `PROCESSED` (or increments `retry_count` with exponential backoff on failure).
- **Consequences & Trade-offs:**
  - **Pros:**
    - **At-Least-Once Delivery Guarantee:** Domain mutations and event emission are atomically bound to a single PostgreSQL commit.
    - **Short Lock Duration:** Keeps the quote approval transaction under 5 ms (pure SQL), avoiding holding `SELECT ... FOR UPDATE` locks during WeasyPrint PDF rendering (~400 ms).
    - **Idempotent Consumers:** Workers are designed to be idempotent—re-processing `QuoteApprovedEvent` simply overwrites the deterministic MinIO key `proposals/{org_id}/{quote_id}.pdf` and updates `pdf_sha256_hash`.
  - **Cons:**
    - Adds a polling interval (~1–2 seconds) before async side effects start, plus table maintenance for `outbox_events` (mitigated by a partial index `WHERE status = 'PENDING'`).
  - **Implementation Nuance (Phase 4 — Cryptographic Preimage & `SKIP LOCKED`):**
    - Because a PDF cannot contain its own final SHA-256 digest in plain text prior to hashing, the embedded QR Code encodes the canonical proposal/verification URL (`https://bravo-erp.dev/public/quotes/{public_token}` + quote metadata), WeasyPrint renders the final binary PDF, and `hashlib.sha256(pdf_bytes).hexdigest()` is persisted on `quotes.pdf_sha256_hash` (`UNIQUE CHAR(64)`). The public verifier (`GET /api/v1/verify/{pdf_sha256_hash}`) then validates document authenticity and live hardware warranty status against that digest.
    - `outbox_relay.py` and `warranty_cron.py` use `.with_for_update(skip_locked=True).execution_options(populate_existing=True)` so concurrent Taskiq worker processes can poll `outbox_events` and `work_orders` without blocking one another or double-processing events.

---

## ADR-006: Hybrid CachyOS Linux Docker Compose Watch Strategy (Bind Mounts for Source + Anonymous Volumes for `.venv`/`node_modules` + Lockfile Rebuild)

- **Status:** Accepted (2026-10-29)
- **Context:**
  Developing on Arch Linux (CachyOS) while running everything in Docker (`docker-compose.dev.yml`) presents a classic tension:
  - Mounting the entire `./backend` or `./frontend` directory into the container overwrites the container's `/app/.venv` and `/app/node_modules` with the host's directories, causing ELF binary/glibc mismatches or permission conflicts.
  - Conversely, using `develop.watch` `sync` action without bind mounts copies files over the Docker socket rather than leveraging native Linux kernel `inotify` events.
- **Decision:**
  Use a **Hybrid CachyOS Linux Strategy** in `docker-compose.dev.yml`:
  1. Bind-mount **only source code subdirectories** (`./backend/src:/app/src`, `./backend/tests:/app/tests`, `./backend/migrations:/app/migrations`, `./frontend/src:/app/src`, `./frontend/public:/app/public`) for zero-latency Linux kernel `inotify` hot-reload.
  2. Isolate `/app/.venv`, `/app/node_modules`, and `/app/.next` inside **anonymous container volumes** so host IDE tools (`mypy`, `ruff`, `tsserver`) and container runtimes never interfere.
  3. Configure `develop.watch` with `action: rebuild` exclusively on dependency manifest/lockfile paths (`backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/pnpm-lock.yaml`).
- **Consequences & Trade-offs:**
  - **Pros:**
    - Instantaneous (<10 ms) hot-reload on both `uvicorn --reload`, `taskiq --reload`, and `next dev --turbopack`.
    - Zero host/container virtual environment corruption.
    - Automatic container rebuild whenever an agent runs `uv add` or `pnpm add` on the host.
  - **Cons:**
    - Requires running `docker compose -f docker-compose.dev.yml down -v` if anonymous volumes ever need a full manual purge.
  - **Implementation Nuances (Phase 0 & Phase 1):**
    - `backend/pyproject.toml` configures `[tool.uv.build-backend]` with `module-name = "src"`, `module-root = ""`, a PEP 561 `backend/src/py.typed` marker, and `mypy_path = "$MYPY_CONFIG_FILE_DIR"` so `mypy --strict` works identically whether invoked from the repo root or inside `backend/`.
    - `frontend/Dockerfile.dev` passes `--config.strict-dep-builds=false` to `pnpm install --frozen-lockfile` so `pnpm v11` does not abort non-interactive container builds on optional native resolver postinstall scripts (`unrs-resolver`).
    - Because upstream `minio/minio` and `minio/mc` images on Docker Hub/Quay now require registry authentication, `docker-compose.dev.yml` uses Chainguard's public, hardened `cgr.dev/chainguard/minio:latest-dev` and `cgr.dev/chainguard/minio-client:latest-dev` images, and maps host `POSTGRES_PORT` (`5433` in local `.env` when `5432` is occupied by other host containers).

---

## ADR-007: Monetary Values Stored Strictly as Integer Cents (`_cents`) in Database and API Contracts to Prevent Floating-Point Rounding Errors

- **Status:** Accepted (2026-10-29)
- **Context:**
  Commercial proposals in `bravo-erp` aggregate dozens of auto-derived line items (baluns, connectors, cable meters, cameras, DVRs, HDDs, labor) and compute total cost, total sale price, and profit margin. Representing currency as IEEE 754 floating-point numbers (`float` in Python / `number` in JSON) introduces binary representation errors (e.g., `0.1 + 0.2 = 0.30000000000000004`), causing 1-cent discrepancies between line-item sums and invoice totals.
- **Decision:**
  Store and transmit all monetary amounts strictly as **64-bit/32-bit signed integers representing Brazilian Real centavos (`_cents`)** across PostgreSQL columns (`cost_price_cents`, `sale_price_cents`, `unit_cost_cents`, `unit_sale_cents`, `total_cost_cents`, `total_sale_cents`), Pydantic v2 schemas, and TypeScript interfaces. For example, `R$ 1.499,90` is represented as `149990`. Percentage margins (`margin_percent`) use exact decimal arithmetic (`Decimal` / `NUMERIC(6,2)`).
- **Consequences & Trade-offs:**
  - **Pros:**
    - **100% Exact Integer Arithmetic:** Additions and quantity multiplications (`quantity * unit_sale_cents`) are mathematically exact across Python, PostgreSQL, and TypeScript.
    - **Explicit Naming Convention:** Suffixing every monetary field with `_cents` eliminates unit ambiguity for both human engineers and AI agents.
  - **Cons:**
    - Frontend UI components and Jinja2 PDF templates must format integer cents to `pt-BR` currency strings (`Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(cents / 100)`), which is centralized in a single shared currency formatter helper.
