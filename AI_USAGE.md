# AI Usage

## Tools used

- **Claude Code (claude-sonnet-4-6)** — primary implementation agent running in the CLI
- **Explore subagent** — codebase discovery (directory tree, all existing file contents)
- **Plan subagent** — architectural design before implementation

## Approach

The session started by exiting Plan Mode and executing the implementation plan directly in the main agent.

### Key prompts / transcript excerpts

**Initial exploration prompt** (to Explore agent):
> "Explore the codebase thoroughly. I need the full directory structure and contents of all key files: settings.py, urls.py, pyproject.toml, all files under app/ds/, all Terraform files, and CHALLENGE.md."

**Implementation** (main agent, writing files in parallel batches):
1. Domain layer (entities + ports) — pure Python dataclasses and Protocols
2. Infrastructure layer (models, checkpoint, lake writer, event emitter, search index, DI container)
3. Use-case layer (ingest + search)
4. Adapter layer (Django ORM repositories, Django views)
5. App config + migrations
6. Tests (17 `SimpleTestCase` tests, no DB)
7. Terraform fixes, documentation

## What was verified manually

- `manage.py test app.ds` — 17/17 tests pass
- `ruff check` + `ruff format --check` — no lint issues after auto-fix
- `manage.py check` — no Django system check issues
- `docker compose up` — Postgres + LocalStack + Django start cleanly

### Specific edge cases verified

- Dry-run does not advance checkpoint, write lake, or emit events
- Checkpoint uses `os.replace()` (POSIX-atomic) — no partial writes on crash
- Re-running ingest with no new rows keeps checkpoint at current value
- Search index rebuilt from full lake (all date partitions) after each ingest, not just delta
- Search results stable-sorted by `(-score, case_id)` for full determinism including ties
- Empty index returns `[]` not an error

## Mistakes and corrections

1. **`FakeSearchIndex._make_use_case` used `rows or CASES`** — for `rows=[]`, this evaluated to `CASES` (empty list is falsy). Fixed to `CASES if rows is None else rows`.

2. **`search_index.rebuild_from_lake_rows(case_rows)` only passed delta rows** — the initial plan would have cleared the index on subsequent ingests with no new rows. Fixed by having the use case call `rebuild_from_lake(lake_dir)` which reads all date partitions and deduplicates by `id`.

3. **Wrong Python path** — initial test run used the repo-root `.venv` (Python 3.10, missing psycopg). Fixed by running from `backend/` against `backend/.venv` (Python 3.14.2 with all deps).

4. **Ruff lint issues** — unused imports (`json`, `os` in tests; `numpy` unused import in conditional branch), un-quoted type annotation, un-sorted migration imports. All auto-fixed with `ruff --fix`.
