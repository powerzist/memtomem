# Claude Code notes — memtomem

Markdown-first long-term memory MCP server (LTM). For what it does see
`README.md`; for setup, architecture, and project layout see `CONTRIBUTING.md`
and `docs/guides/`. This file only captures the few things Claude Code needs
in context that aren't obvious from those docs.

## Commands

Requires Python 3.12+ and `uv` (workspace-managed monorepo).

```bash
uv pip install -e "packages/memtomem[all]"             # install deps
uv run pytest -m "not ollama"                          # tests (CI filter)
uv run ruff check packages/memtomem/src && \
    uv run ruff format --check packages/memtomem/src   # lint (required)
uv run mypy packages/memtomem/src                      # typecheck (advisory)
```

The `ollama` marker auto-skips when Ollama isn't running; CI always uses
`-m "not ollama"`. `ruff` and tests must pass to merge; `mypy` is advisory.
CLI entry points live in `packages/memtomem/pyproject.toml` — `mm` is an alias
for `memtomem` and both resolve to `memtomem.cli:cli`.

## Invariants when editing

- **No Python-level dependency on `memtomem-stm`.** The STM proxy lives in a
  separate repo ([memtomem/memtomem-stm](https://github.com/memtomem/memtomem-stm))
  and talks to this LTM server only through the MCP protocol. Don't
  `import memtomem_stm` from `packages/memtomem/src/`, and don't hand-roll an
  in-process STM client — cross-repo coupling is explicitly forbidden.
- **`mm` ≡ `memtomem`.** Both `project.scripts` entries in
  `packages/memtomem/pyproject.toml` resolve to `memtomem.cli:cli` — keep them
  in sync, don't diverge behavior or add flags to only one name.
- **Search pipeline order is fixed**: query expansion → BM25 + dense (parallel)
  → RRF fusion → time-decay → optional cross-encoder rerank → MMR → access-freq
  boost → importance boost → context-window expansion. Don't reorder stages in
  `packages/memtomem/src/memtomem/search/pipeline.py` without updating the
  "Search pipeline" section in `docs/guides/user-guide.md`.
- **MCP tools go through the registry.** New tools use `@register` from
  `server/tool_registry.py` + `@tool_handler` — no direct `@mcp.tool()`. Add
  imports in `server/__init__.py` and classify the tool into
  `_CORE_TOOLS` / `_STANDARD_TOOLS` / full; the `mem_do` meta-tool routes
  non-core actions. Don't change the default mode (`core` = 9 tools).
- **Line length 100**, target `py312` (`tool.ruff`, `tool.mypy` in root
  `pyproject.toml`). `.claude/`, `scripts/`, and `CLAUDE.local.md` are
  gitignored — don't commit anything under them, and don't assume other
  contributors have the same contents there.

## PRs

Branch from `main`, one focused change per PR, add tests for new behavior, and
write commit messages that explain the "why". See `CONTRIBUTING.md` for the
full checklist and the STM decoupling rules in `packages/memtomem/README.md`.
