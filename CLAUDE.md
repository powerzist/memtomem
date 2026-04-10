# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is memtomem?

Markdown-first, long-term memory infrastructure for AI agents. Provides hybrid BM25 + semantic search across indexed markdown/JSON/YAML/code files via MCP (Model Context Protocol).

## Build & Development Commands

```bash
# Install (uv workspace — Python 3.12+)
uv pip install -e "packages/memtomem[all]"

# Run all tests (pytest + pytest-asyncio, async tests auto-detected)
uv run pytest                      # 907 tests

# Run a single test file
uv run pytest packages/memtomem/tests/test_search.py -v

# Run a single test by name
uv run pytest packages/memtomem/tests/test_search.py::test_bm25_search -xvs

# Skip tests requiring a running Ollama instance
uv run pytest -m "not ollama"

# Lint and format (ruff, line-length=100, target py312)
uv run ruff check packages/memtomem/src --fix
uv run ruff format packages/memtomem/src

# Type check
uv run mypy packages/memtomem/src

# Run MCP server
uv run memtomem-server

# Run CLI
uv run memtomem search "query"    # or: mm search "query"

# Run web UI
uv run memtomem-web               # http://localhost:8080
```

## Architecture

**Single-package monorepo** managed by uv workspace:

- `packages/memtomem/` — Core: MCP server, CLI, web UI, search, storage, indexing
- `packages/memtomem-claude-plugin/` — Claude Code plugin (experimental, not yet published)
- `packages/memtomem-openclaw-plugin/` — OpenClaw plugin (experimental, not yet published)

The STM proxy gateway lives in a separate repository: [memtomem/memtomem-stm](https://github.com/memtomem/memtomem-stm). Communication with this repo's MCP server happens entirely through the MCP protocol — no direct code coupling.

### Dependency injection: AppContext

All services live in `AppContext` (dataclass in `server/context.py`). Every MCP tool receives `ctx: CtxType` and calls `_get_app(ctx)` to access config, storage, embedder, index engine, search pipeline, and file watcher. The lifespan (`server/lifespan.py`) initializes all services at startup.

### MCP tools

73 tools registered via `@register` decorator (in `server/tool_registry.py`) in `server/tools/*.py`, imported in `server/__init__.py`. Each tool is wrapped with `@tool_handler` for error handling. Tool visibility is controlled by `MEMTOMEM_TOOL_MODE` env var (`core`=9 tools including `mem_do`, `standard`=~32 + `mem_do`, `full`=73). Default mode is `core`. The `mem_do` meta-tool routes to 64 non-core actions via `mem_do(action="...", params={...})`. Action aliases (e.g. `health_report` → `eval`) are supported for discoverability. The `mem_expand` action provides targeted context expansion for individual search results.

### Storage: SQLite + FTS5 + sqlite-vec

`SqliteBackend` in `storage/sqlite_backend.py` combines multiple mixins (Session, Scratch, Relation, Analytic, History, Entity, Policy) for different domains. Uses a read pool (3 read-only connections) + write lock. Vector search via `sqlite-vec` extension with F32 serialization.

### Search pipeline

`search/pipeline.py` runs a multi-stage pipeline:
1. Query expansion (tags/headings)
2. Parallel BM25 (FTS5) + dense (sqlite-vec cosine) retrieval
3. RRF (Reciprocal Rank Fusion) merging
4. Optional time-decay scoring
5. Optional cross-encoder reranking
6. MMR diversification
7. Access-frequency boost
8. Importance boost
9. Context-window expansion (±N adjacent chunks from same source file)

Results cached with 30s TTL. Context expansion uses batch `list_chunks_by_sources()` (single DB query). Per-call override via `search(context_window=N)` or global via `ContextWindowConfig`.

### Chunking

`chunking/` module with specialized chunkers: markdown (heading-aware sections), Python (AST-based), JS/TS (tree-sitter), structured data (JSON/YAML/TOML). Registry pattern in `chunking/registry.py`. Incremental re-indexing via SHA-256 content hashing — only changed chunks get re-embedded.

### Embedding providers

`embedding/` supports Ollama (local, default `nomic-embed-text` 768-dim) and OpenAI (cloud). Batch processing with configurable batch size and concurrency.

### Configuration

All config via `MEMTOMEM_` prefixed env vars with `__` nesting (e.g., `MEMTOMEM_EMBEDDING__PROVIDER=openai`). Pydantic-settings classes in `config.py`.

### STM proxy gateway (separate repo)

The STM proxy gateway lives in [memtomem/memtomem-stm](https://github.com/memtomem/memtomem-stm). It is not part of this repository — refer to that repo's CLAUDE.md and README for its architecture (4-stage CLEAN → COMPRESS → SURFACE → INDEX pipeline, surfacing engine, compression strategies, etc.). STM communicates with this core repo's MCP server entirely through the MCP protocol; there is no direct code coupling and no `from memtomem.*` imports allowed in STM code.

## Testing

- Framework: pytest + pytest-asyncio (asyncio_mode = "auto")
- Test root: `packages/memtomem/tests/` (907 tests)
- Configured in `pyproject.toml` `testpaths`
- Fixtures in `conftest.py` create isolated SQLite DB per test
- Marker `@pytest.mark.ollama` for tests requiring a running Ollama instance (auto-skipped if unavailable)

## Adding new MCP tools

1. Create module in `server/tools/`
2. Implement async function with `@register` decorator (from `server/tool_registry.py`) and `@tool_handler`
3. Import in `server/__init__.py`
4. Add to appropriate tool mode set (`_CORE_TOOLS`, `_STANDARD_TOOLS`, or full by default)

The `@register` decorator in `server/tool_registry.py` replaces direct `@mcp.tool()` usage. The meta-tool implementation lives in `server/tools/meta.py`.
