---
trigger: always_on
description: Mandatory AI Agent operational protocol, CLI-first rules, living documentation sync, and strict quality gates for bravo-erp.
---

# `bravo-erp` — Mandatory Workspace Governance Rule

Every Antigravity session operating in this workspace MUST follow this 4-step operational protocol on every task:

1. **Mandatory Startup Action (Context Ingestion):**
   - Always read `AGENTS.md` and `PLAN.md` at the start of any task.
   - Inspect the relevant domain sections of `SPEC.md` and `DECISIONS.md` before proposing changes, generating migrations, or writing code.

2. **Living Documentation Sync (Scope Change Capture):**
   - Whenever the user introduces a new idea, changes a business rule, refines a formula, or alters an architectural decision mid-conversation, you MUST update `SPEC.md`, `DECISIONS.md`, and `PLAN.md` **first** before writing or modifying application code.

3. **CLI-First Execution (Token Economy):**
   - Never hand-write framework boilerplate (`pyproject.toml`, `package.json`, `tsconfig.json`, Alembic migration skeletons, or `shadcn/ui` primitive components) from scratch when a deterministic CLI generator (`uv`, `alembic`, `pnpm`, `shadcn`) exists.

4. **Definition of Done (Quality Gate):**
   - Never mark a task as `[x]` in `PLAN.md` until all Quality Gate checks pass with `0` errors:
     - Backend: `uv run --project backend ruff check backend/src backend/tests`, `uv run --project backend ruff format --check backend/src backend/tests`, `uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests --strict`, and `uv run --project backend pytest backend/tests -v`.
     - Frontend: `pnpm -C frontend typecheck` (`pnpm -C frontend exec tsc --noEmit`) and `pnpm -C frontend lint`.
