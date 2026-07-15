# TUI rebuild behavior decision gates

> **Post-baseline implementation artifact:** This file was created during the
> Phase 0 implementation run after the original 2026-07-15 TUI handoff plan and
> memtomem memory were written. It is not part of either initial baseline.
> Removing this file does not modify or roll back the initial plan or memory.
> Approved decisions copied into the plan are separately bounded by amendment
> markers with their own rollback instructions.

This document characterizes the eleven behavior conflicts identified by the
2026-07-15 rebuild audit. It records observed behavior only. A row remains
`pending-user-decision` until the user explicitly chooses the TUI policy; the
TUI must not silently inherit or repair the behavior.

## 1. Tokenizer change and FTS rebuild

- Status: `pending-user-decision`
- Observed CLI behavior: `config set search.tokenizer ...` calls the async
  `SqliteBackend.rebuild_fts()` method without awaiting it, then formats the
  coroutine object as if it were a completed chunk count.
- Evidence: `cli/config_cmd.py:107-118`, `storage/sqlite_backend.py:1031`;
  the current mock-based test in `tests/test_cli.py:192-202` does not expose
  the async mismatch.
- Alternatives: reproduce the current broken success output; or await the
  rebuild and report its real result while preserving all other ordering and
  persistence semantics.

## 2. `config.d` merge during config mutation

- Status: `pending-user-decision`
- Observed CLI behavior: `config show` loads `config.d` and then overrides,
  while `config set` starts from defaults plus overrides only before saving.
  Values supplied only by `config.d` can therefore be absent from the set/save
  comparand and resulting override calculation.
- Evidence: `cli/config_cmd.py:32-42` versus `cli/config_cmd.py:68-96`.
- Alternatives: match the set/save path exactly; or merge `config.d` before a
  TUI mutation so the persisted override is calculated from the effective
  runtime config.

## 3. Embedding `revert-to-stored`

- Status: `pending-user-decision`
- Observed CLI behavior: the CLI prints that the runtime was reverted but only
  reads the stored values and emits text. The MCP implementation mutates the
  in-memory config and replaces the embedder, search pipeline, and index engine.
- Evidence: `cli/embedding_cmd.py:104-116` versus
  `server/tools/status_config.py:290-352`.
- Alternatives: preserve the CLI no-op-with-success-like-output; or perform the
  structured runtime swap used by MCP and explicitly report persistence scope.

## 4. Reset when chunks are already zero

- Status: `pending-user-decision`
- Observed CLI behavior: reset returns immediately when `total_chunks == 0`,
  before confirmation and `reset_all()`, even though sessions, history, or
  other tables may still contain rows.
- Evidence: `cli/reset_cmd.py:35-54`.
- Alternatives: retain chunk-count short-circuiting; or preview every affected
  table and reset any non-empty state.

## 5. Streaming index root containment

- Status: `pending-user-decision`
- Observed CLI behavior: non-stream `index_path()` rejects paths outside
  configured user/project roots. `index_path_stream()` resolves and discovers
  the requested file or directory without the same root gate; the CLI's normal
  live-progress path uses this streaming API.
- Evidence: `indexing/engine.py:446-454`, `indexing/engine.py:997-1028`, and
  `cli/_index_progress.py:175-183`.
- Alternatives: reproduce the streaming exception; or apply the same root
  containment contract to both paths before discovery.

## 6. Search-cache invalidation after mutations

- Status: `pending-user-decision`
- Observed CLI behavior: only selected one-shot mutations explicitly call
  `search_pipeline.invalidate_cache()`; many CLI write paths omit it because
  the process exits immediately. MCP's long-lived mutation handlers invalidate
  the live cache much more consistently.
- Evidence: CLI call sites are currently limited to
  `cli/context_cmd.py:3462` and `cli/ingest_cmd.py:267`, while server mutation
  handlers call it throughout `server/tools/`.
- Alternatives: mirror each one-shot omission; or require every relevant TUI
  mutation to invalidate the persistent runtime cache after success/partial
  success according to its written state.

## 7. Current-session state concurrency

- Status: `pending-user-decision`
- Observed CLI behavior: the current session ID is written directly with
  `Path.write_text()` and cleared with `unlink()`, without a lock or atomic
  replace. Concurrent processes can race.
- Evidence: `cli/session_cmd.py:77-100`.
- Alternatives: preserve direct last-writer-wins behavior; or use an atomic,
  locked TUI-owned session-state service with an explicit conflict policy.

## 8. Memory add and agent share partial writes

- Status: `pending-user-decision`
- Observed CLI behavior: both flows append the markdown entry before indexing.
  Memory add performs tag updates after indexing. A later failure can therefore
  leave a durable file append with missing index rows or missing tag updates;
  agent share has the same append-before-index boundary.
- Evidence: `cli/memory.py:221-245` and `cli/agent_cmd.py:280-313`.
- Alternatives: preserve the non-atomic sequence and expose a structured
  partial result/recovery action; or introduce rollback/transaction behavior
  where the filesystem and storage boundaries can support it.

## 9. Mutable bootstrap versus read-only diagnostics

- Status: `approved-2026-07-15`
- Observed CLI behavior: ordinary component bootstrap initializes storage and
  may create or migrate database state. Memory doctor deliberately loads config
  with migration disabled and opens existing data read-only.
- Evidence: `server/component_factory.py:47-100` versus
  `cli/memory_doctor_cmd.py:286-306` and `cli/memory_doctor_cmd.py:338-370`.
- Decision: Home and Status use a no-create/no-migrate reader. Search may open
  the normal TUI runtime and perform the DB schema initialization/migration
  required by real search behavior, but it must never auto-index files or build
  missing embeddings. BM25-only configurations remain valid without vectors;
  absent index data or incompatible embeddings produce an actionable state
  instead of an implicit rebuild.

## 10. Context `--yes` / `--apply` enforcement

- Status: `pending-user-decision`
- Observed CLI behavior: help says `--yes` requires `--apply` for settings and
  memory migration, but those commands return a dry-run normally when `--yes`
  is supplied without `--apply`. The adjacent general context migrate command
  raises a usage error for the same combination.
- Evidence: `cli/context_cmd.py:2413-2476`, `cli/context_cmd.py:2773-2863`, and
  `cli/context_cmd.py:2991-3038`.
- Alternatives: preserve each command's current enforcement; or adopt one
  consistent preview/apply validation rule across native TUI migrations.

## 11. Agent namespace migration safety default

- Status: `pending-user-decision`
- Observed CLI behavior: `agent migrate` applies by default; `--dry-run` turns
  mutation off. This is the inverse of the preview-first pattern used by other
  migrations.
- Evidence: `cli/agent_cmd.py:34-71`; behavior tests in
  `tests/test_agent_cmd.py:43-74`.
- Alternatives: preserve apply-by-default; or make the TUI workflow
  consequence-first with preview followed by explicit apply.

## First vertical-slice decision

Gate 9 was approved by the user on 2026-07-15. Gates 1-8 and 10-11 remain
blocked before their corresponding mutating workflows are built. The approved
Phase 4 split is:

- Home and Status use a no-create/no-migrate diagnostic reader.
- Search activates the normal TUI runtime because executing a real search
  requires initialized storage, configured embedder when applicable, and a
  search pipeline. It does not create index content or missing vectors.
- The UI labels the transition if opening Search would initialize or migrate
  state that Home only inspected.

Approval covers this diagnostic/runtime boundary only; it does not resolve any
other decision gate.
