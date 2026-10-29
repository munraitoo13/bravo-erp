# `AGENTS.md` — AI Agent Operational Constitution & Master Manual

> **MANDATORY DIRECTIVE FOR ALL AI AGENTS (`antigravity` / `antigravity-cli`):**
> This document is the supreme operational constitution for the `bravo-erp` repository. Every AI agent session MUST read this file in full before inspecting code, proposing changes, or executing commands. Deviation from the workflows, typing rules, or CLI-first mandates defined herein is strictly forbidden.

---

## 1. Project Identity & Language Governance

`bravo-erp` is a production-grade, multi-tenant B2B SaaS and Technical ERP purpose-built for Electronic Security and CCTV (CFTV) Installation Companies (specializing in the Intelbras Multi-HD MHDX analog and IP NVD hardware ecosystems).

It serves two primary objectives:
1. **Real-World Field Operations:** Automated engineering sizing (storage, hybrid channel allocation, electrical current draw, voltage drop, and accessory BOM derivation), commercial quote lifecycle management, field work order execution, and hardware serial-number/warranty tracking.
2. **Staff/Senior Engineering Showcase:** Designed to withstand rigorous architectural scrutiny, featuring a clean Modular Monolith architecture, 100% async I/O (`FastAPI` + `SQLAlchemy 2.0 AsyncSession` + `Taskiq`), pessimistic inventory locking (`SELECT ... FOR UPDATE`), a transactional outbox (`outbox_events`), RFC 7807 error contracts, and a zero-friction 1-Click Recruiter Demo Mode.

### Strict Language Standard
- **100% English (Mandatory):** All source code, module names, variable/function/class identifiers, database table and column names, enum keys, REST API URIs, JSON keys, code comments, docstrings, Git commit messages, and Markdown governance documentation (`AGENTS.md`, `SPEC.md`, `DECISIONS.md`, `PLAN.md`, `README.md`) MUST be written in English.
- **Brazilian Portuguese (`pt-BR`) (Strictly Scoped):** Restricted **exclusively** to:
  1. User-facing Frontend UI labels, notifications, and PDF proposal templates.
  2. Database seed data (`name_pt_br`, realistic Brazilian CCTV terminology, and Intelbras/WD Purple/Condutti product catalogs).

---

## 2. Mandatory Agent Workflow Loop (The Golden Protocol)

Every AI agent interacting with this repository MUST execute the following 4-step lifecycle on **every prompt and task**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. CONTEXT INGESTION                                                    │
│    Read AGENTS.md + PLAN.md -> Inspect relevant SPEC.md & DECISIONS.md  │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. SCOPE CHANGE & IDEA CAPTURE PROTOCOL                                 │
│    If user alters requirements/rules/architecture -> Update SPEC.md,    │
│    DECISIONS.md, and PLAN.md FIRST before touching application code.    │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. CLI-FIRST EXECUTION & DOMAIN IMPLEMENTATION                          │
│    Run deterministic CLI generators for scaffolding/deps/migrations.    │
│    Write strictly typed domain/service/UI code with zero `Any`.         │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. QUALITY GATE & DOCUMENTATION SYNC                                    │
│    Pass ruff + mypy --strict + pytest + tsc + eslint -> Update PLAN.md  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Step 1: Context Ingestion (Before Acting)
1. Read `AGENTS.md` (this file) and `PLAN.md` to identify the active phase, current milestone (`[~]`), and next pending task (`[ ]`).
2. Read the corresponding sections of `SPEC.md` (database schema, mathematical formulas, state machines, API contracts) and `DECISIONS.md` (ADRs) before writing or modifying any file.
3. Never guess domain formulas, table column names, or status enum values—always cross-reference `SPEC.md`.

### Step 2: Scope Change & Idea Capture Protocol (Mid-Conversation Pivots)
When the user introduces a new feature idea, modifies a mathematical formula, changes a state transition rule, or requests an architectural adjustment during a conversation:
1. **STOP** before editing any `.py` or `.ts`/`.tsx` file.
2. **Update `SPEC.md` first** so the specification reflects the new source of truth.
3. **Update `DECISIONS.md`** (append a new ADR or supersede an existing one) if the change affects architectural trade-offs, tooling, concurrency, or data modeling.
4. **Update `PLAN.md`** to add, split, or reprioritize atomic tasks.
5. **Only after the governance docs are updated** may you implement the change in source code.

### Step 3: CLI-First Execution (Token Economy Rules)
To maximize token efficiency and eliminate hallucinated configuration files, agents must strictly obey the **CLI-First Generation Rule**:
- **FORBIDDEN:**
  - Manually writing `pyproject.toml`, `package.json`, `tsconfig.json`, `alembic.ini`, or Alembic migration files from scratch when a CLI generator exists.
  - Hand-coding `shadcn/ui` primitive components inside `frontend/src/components/ui/`.
  - Editing lockfiles (`uv.lock`, `pnpm-lock.yaml`) manually.
- **MANDATORY (Non-Interactive CLI Commands):**
  - **Backend project initialization:**
    ```bash
    uv init --app --python 3.12 backend
    ```
  - **Backend dependency management:**
    ```bash
    uv add --project backend <package_name>
    uv add --project backend --dev <dev_package_name>
    ```
  - **Alembic initialization & migration generation:**
    ```bash
    uv run --project backend alembic init -t async backend/migrations
    docker compose -f docker-compose.dev.yml exec backend uv run alembic revision --autogenerate -m "<descriptive_snake_case_message>"
    docker compose -f docker-compose.dev.yml exec backend uv run alembic upgrade head
    ```
  - **Frontend project initialization & dependency management:**
    ```bash
    pnpm create next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-pnpm --yes
    pnpm --dir frontend add <package_name>
    pnpm --dir frontend add -D <dev_package_name>
    ```
  - **shadcn/ui initialization & component installation:**
    ```bash
    pnpm --dir frontend dlx shadcn@latest init -d -y
    pnpm --dir frontend dlx shadcn@latest add button card input label select table badge dialog tabs form sonner dropdown-menu separator sheet skeleton alert -y
    ```

### Step 4: Quality Gate & Definition of Done (Before Finishing Turn)
No task in `PLAN.md` may ever be transitioned from `[~]` to `[x]` unless **every single check below exits with code `0`**:
1. **Backend Linter & Formatter (`ruff`):**
   ```bash
   uv run --project backend ruff check backend/src backend/tests
   uv run --project backend ruff format --check backend/src backend/tests
   ```
2. **Backend Strict Static Type Checker (`mypy --strict`):**
   ```bash
   uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests --strict
   ```
3. **Backend Automated Test Suite (`pytest` + `testcontainers`):**
   ```bash
   uv run --project backend pytest backend/tests -v
   ```
4. **Frontend TypeScript Compiler & ESLint:**
   ```bash
   pnpm -C frontend exec tsc --noEmit
   pnpm -C frontend lint
   ```
5. **Documentation Synchronization:**
   - Mark completed tasks as `[x]` in `PLAN.md` and update the **Current Session Handoff Notes** block at the top of `PLAN.md`.
   - Record any newly discovered technical nuances in `DECISIONS.md`.

---

## 3. Coding Standards & Anti-"AI Code Smell" Rules

### 3.1. Python 3.12+ & FastAPI Conventions
- **Modern Typing Syntax Only (PEP 585 / PEP 604 / PEP 695):**
  - Always use built-in generic types: `list[str]`, `dict[str, int]`, `tuple[int, ...]`, `set[UUID]`.
  - Always use union pipe syntax: `str | None`, `int | float`.
  - Use the `type` statement for type aliases (`type JSONDict = dict[str, object]`).
  - **FORBIDDEN:** Importing `List`, `Dict`, `Tuple`, `Set`, `Optional`, or `Union` from `typing`.
- **Zero `Any` Tolerance (`mypy --strict`):**
  - Every function, method, dependency, and test fixture MUST have explicit parameter and return type annotations (including `-> None`).
  - Do not use `Any` or `# type: ignore` to silence type errors. Use `TypedDict`, `Protocol`, `Pydantic BaseModel`, or discriminated unions instead.
- **Thin Routers (`router.py`):**
  - FastAPI route handlers MUST be thin controllers (~5–15 lines).
  - A route handler may ONLY:
    1. Validate and parse request parameters/body via Pydantic v2 schemas.
    2. Inject `CurrentTenantContext`, `AsyncSession` (or Service dependency), and `Correlation-ID`.
    3. Delegate execution to a module `Service` method.
    4. Return a role-appropriate Pydantic v2 response model.
  - **FORBIDDEN:** Writing SQLAlchemy `select()`/`insert()`/`update()` queries, state machine rules, or engineering calculations directly inside `router.py`.
- **Pydantic v2 Idioms:**
  - Use `model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")` where appropriate.
  - Use `@field_validator` and `@model_validator(mode="after")`.
  - **FORBIDDEN:** Legacy Pydantic v1 methods (`.dict()`, `.parse_obj()`, `@validator`, `class Config:`). Always use `.model_dump()`, `.model_validate()`, and `ConfigDict`.

### 3.2. SQLAlchemy 2.0 Async Rules
- **100% SQLAlchemy 2.0 Syntax:**
  - Models MUST use `Mapped[T]` and `mapped_column(...)` declarative typing.
  - Queries MUST use `select(...)`, `insert(...)`, `update(...)`, `delete(...)` executed via `await session.execute(...)` or `await session.scalars(...)`.
  - **FORBIDDEN:** Legacy 1.x `session.query(...)` syntax under any circumstance.
- **Async Relationship Loading:**
  - All ORM relationships must set `lazy="raise"` or `lazy="selectin"` explicitly so accidental implicit synchronous I/O (`MissingGreenlet`) is impossible.
  - Use explicit `.options(selectinload(...))` or `.options(joinedload(...))` in repository queries.
- **Transaction Boundaries (Unit of Work):**
  - Repositories (`repository.py`) execute SQL statements against the injected `AsyncSession` and may call `await session.flush()`, but **MUST NEVER call `await session.commit()`**.
  - Transaction commits (`async with session.begin():` or `await session.commit()`) belong exclusively to the Service / Use-Case orchestration layer so multi-repository operations (e.g., locking inventory + updating quote status + creating work order + writing audit log + inserting outbox event) succeed or roll back atomically.

### 3.3. Error Handling, RFC 7807 & Observability
- **Forbidden Exception Antipatterns:**
  - **FORBIDDEN:** Bare `except Exception:` blocks that swallow errors or log-and-return `None`.
  - **FORBIDDEN:** Raising `fastapi.HTTPException` inside `domain/`, `service.py`, or `repository.py`.
- **Typed Domain Exceptions -> RFC 7807 (`application/problem+json`):**
  - Domain and Service layers raise structured subclasses of `DomainError` defined in `backend/src/core/exceptions.py`:
    - `ResourceNotFoundError` -> HTTP `404 Not Found`
    - `InvalidStateTransitionError` -> HTTP `422 Unprocessable Content`
    - `DomainValidationError` -> HTTP `422 Unprocessable Content`
    - `InsufficientStockError` -> HTTP `409 Conflict`
    - `ConcurrencyConflictError` -> HTTP `409 Conflict`
    - `AuthenticationFailedError` -> HTTP `401 Unauthorized`
    - `TenantAccessDeniedError` / `RolePermissionDeniedError` / `DemoProtectionError` -> HTTP `403 Forbidden`
  - A single global FastAPI exception handler converts all `DomainError` instances (and `RequestValidationError`) into **RFC 7807 Problem Details** responses with media type `application/problem+json`:
    ```json
    {
      "type": "https://bravo-erp.dev/errors/insufficient-stock",
      "title": "Insufficient Stock for Quote Approval",
      "status": 409,
      "detail": "Catalog item 'DVR Intelbras MHDX 1108' (SKU: MHDX-1108) has 0 available units (requested: 1).",
      "instance": "/api/v1/public/quotes/0192d4a0-7c10-7000-8000-000000000001/approve",
      "correlation_id": "req_0192d4a08f3a7b2c9d1e",
      "errors": [
        {
          "catalog_item_id": "0192d4a0-1111-7000-8000-000000000002",
          "sku": "MHDX-1108",
          "available_quantity": 0,
          "requested_quantity": 1
        }
      ]
    }
    ```
- **Structured Logging & Correlation-ID Propagation (`structlog`):**
  - Standard `print()` and unformatted `logging.info(f"...")` calls are **FORBIDDEN**.
  - All logs must use `structlog` with key-value structured events (`logger.info("quote_approved", quote_id=str(quote.id), organization_id=str(ctx.organization_id))`).
  - Every incoming HTTP request extracts or generates an `X-Correlation-ID` header, binds it via `structlog.contextvars.bind_contextvars(correlation_id=...)`, echoes `X-Correlation-ID` on the HTTP response, and embeds `correlation_id` inside `outbox_events.payload` so Taskiq background workers log with the exact same trace ID.

### 3.4. Frontend TypeScript, Next.js App Router & State Rules
- **Strict TypeScript:** `strict: true` and `noUncheckedIndexedAccess: true` in `tsconfig.json`. Zero `any` types (`@typescript-eslint/no-explicit-any: "error"`).
- **Data Fetching & Mutations:** All client-side API interactions use **TanStack Query v5** (`useQuery`, `useMutation`, `queryClient.invalidateQueries`) coupled with a central typed API client (`frontend/src/lib/api-client.ts`) that automatically parses RFC 7807 `application/problem+json` error payloads.
- **Forms & Validation:** All interactive forms use **React Hook Form** + **Zod** (`@hookform/resolvers/zod`).
- **RBAC UI Discipline:** Never rely solely on hiding buttons in React for security. Backend Pydantic response schemas strip sensitive fields (`cost_price_cents`, `total_cost_cents`, `margin_percent`) for `TECHNICIAN` and `PUBLIC_CLIENT` roles, and the Frontend renders role-specific TypeScript union types accordingly.

---

## 4. CachyOS Linux & Docker Compose Watch Command Reference

The development environment runs on **Arch Linux (CachyOS)** using a hybrid Docker Compose Watch setup (`docker-compose.dev.yml`):
- Source directories (`./backend/src`, `./backend/tests`, `./frontend/src`) are bind-mounted from the Linux host for instant kernel `inotify` reload.
- `.venv`, `node_modules`, and `.next` inside containers are isolated via anonymous volumes so host LSP/CLI tools and container runtimes never collide.
- `develop.watch` rules automatically trigger container `rebuild` when `pyproject.toml`, `uv.lock`, `package.json`, or `pnpm-lock.yaml` change.

### 4.1. Starting & Managing the Container Stack
```bash
# Start full stack with live watch (rebuild on lockfile change, native bind mount hot-reload)
docker compose -f docker-compose.dev.yml up --build --watch

# Start stack in detached background mode (preferred for agent automated verification)
docker compose -f docker-compose.dev.yml up --build -d

# Check service health status (all services must report "healthy" or "Exited (0)" for minio-setup)
docker compose -f docker-compose.dev.yml ps

# Tail logs for a specific service
docker compose -f docker-compose.dev.yml logs -f backend worker frontend

# Tear down stack and remove anonymous volumes (clean slate)
docker compose -f docker-compose.dev.yml down -v
```

### 4.2. Host vs. Container Command Execution Matrix

| Operation | Where to Run | Exact Command |
| :--- | :--- | :--- |
| Add/remove Python dependency | **Host** (updates `pyproject.toml` & `uv.lock`; triggers container watch rebuild) | `uv add --project backend <pkg>` |
| Add/remove Node dependency | **Host** (updates `package.json` & `pnpm-lock.yaml`; triggers container watch rebuild) | `pnpm --dir frontend add <pkg>` |
| Add `shadcn/ui` component | **Host** | `pnpm --dir frontend dlx shadcn@latest add <comp> -y` |
| Generate Alembic migration | **Container** (`backend` has live network access to `postgres`) | `docker compose -f docker-compose.dev.yml exec backend uv run alembic revision --autogenerate -m "<msg>"` |
| Apply Alembic migrations | **Container** | `docker compose -f docker-compose.dev.yml exec backend uv run alembic upgrade head` |
| Run Demo Database Seeder | **Container** | `docker compose -f docker-compose.dev.yml exec backend uv run python -m src.seed.demo_seeder` |
| Run `ruff` & `mypy --strict` | **Host or Container** | `uv run --project backend ruff check backend/src backend/tests && uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests --strict` |
| Run `pytest` (Unit tests) | **Host or Container** | `uv run --project backend pytest backend/tests/unit -v` |
| Run `pytest` (Testcontainers integration) | **Host** (uses host Docker daemon) | `uv run --project backend pytest backend/tests/integration -v` |
| Run Frontend Typecheck & Lint | **Host or Container** | `pnpm --dir frontend tsc --noEmit && pnpm --dir frontend lint` |
