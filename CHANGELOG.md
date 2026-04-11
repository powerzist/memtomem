# Changelog

All notable changes will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

## [Unreleased]

### Added
- `examples/notebooks/` — five scenario-based Jupyter notebooks that walk
  through the Python API (`create_components()`, `search_pipeline.search()`,
  `index_engine.index_path()`, storage mixins, and `MemtomemStore` for
  LangGraph). Covers hello-memory, bulk indexing + filters, session /
  scratch / recall, search tuning, and a two-node LangGraph agent. Each
  notebook runs against a throwaway temp directory so it cannot touch the
  user's real `~/.memtomem/` setup.
- Notebook 02 includes a "Korean with the kiwipiepy tokenizer" section
  that prints the token stream produced by `unicode61` vs. `kiwipiepy`
  side by side and runs the same query under each configuration.

## [0.1.0] — 2026-04-08

Initial open-source release.

### Core (memtomem)
- MCP server with 72 tools + `mem_do` meta-tool (63 actions, aliases)
- CLI (`memtomem` / `mm`): init, search, add, recall, index, config, context, shell, web, watchdog
- Web UI dashboard: search, sources, tags, sessions, health report
- Hybrid search pipeline: BM25 (FTS5) + dense vectors (sqlite-vec) + RRF fusion
- Multi-stage pipeline: query expansion → parallel retrieval → RRF → time-decay → reranking → MMR → access boost → context-window expansion
- Context-window search (small-to-big retrieval): `search(context_window=N)` + `mem_expand` action
- Tool modes: `core` (9 tools), `standard` (~32), `full` (72)

### Storage
- SQLite with FTS5, sqlite-vec, WAL mode, read pool (3 connections)
- Mixin architecture: Session, Scratch, Relation, Analytic, History, Entity, Policy
- Incremental indexing with SHA-256 content hashing

### Chunking
- Markdown: heading-aware sections with frontmatter/wikilink support
- Python: AST-based splitting at function/class boundaries
- JavaScript/TypeScript: tree-sitter parsing
- JSON/YAML/TOML: structure-aware splitting

### Embedding
- Ollama (local, default `nomic-embed-text` 768-dim)
- OpenAI (cloud)
- `bge-m3` recommended for multilingual (KR/EN/JP/CN)

### Agent Memory
- Episodic (sessions), working (scratchpad with TTL), procedural (workflows)
- Multi-agent namespaces, cross-references, entity extraction
- Memory policies (auto-archive/expire/tag), consolidation/reflection

### Integrations
- LangGraph adapter (`MemtomemStore`)
- Claude Code plugin (experimental)
- OpenClaw plugin (experimental)

### Security
- XSS: DOMPurify sanitization
- SSRF: private IP/internal host blocking
- Path traversal: source validation, symlink rejection
- SQL injection: all queries parameterized

### Testing
- 886 automated tests
- CI: GitHub Actions (lint, typecheck, test)

### Related projects
- [**memtomem-stm**](https://github.com/memtomem/memtomem-stm) — Short-Term Memory proxy gateway with proactive memory surfacing. Distributed as a separate package; communicates with memtomem core entirely through the MCP protocol.
