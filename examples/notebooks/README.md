# memtomem Interactive Notebooks

Scenario-based Jupyter notebooks that walk through memtomem's Python API. Each
notebook is self-contained, runs against a throwaway temp directory, and never
touches your real `~/.memtomem/` setup.

These notebooks complement the MCP-client-focused
[`docs/guides/hands-on-tutorial.md`](../../docs/guides/hands-on-tutorial.md).
Use the tutorial if you want to drive memtomem from Claude Code / Cursor /
Windsurf; use these notebooks if you want to use memtomem as a Python library
in a data-science, research, or agent-framework workflow.

## Prerequisites

1. **Python 3.12+**
2. **Ollama** running locally with the default embedding model:
   ```bash
   ollama serve
   ollama pull nomic-embed-text
   ```
3. **memtomem + jupyter**:
   ```bash
   # From PyPI
   uv pip install "memtomem[ollama]" jupyter ipykernel

   # Or from a source checkout
   uv pip install -e "packages/memtomem[all]" jupyter ipykernel
   ```
4. **(Notebook 02, Korean section only)** the `kiwipiepy` tokenizer:
   ```bash
   uv pip install "memtomem[korean]"
   ```
5. **(Notebook 05 only)** LangGraph:
   ```bash
   uv pip install langgraph
   ```

## Running the notebooks

```bash
uv run jupyter lab examples/notebooks/
```

Each notebook checks that Ollama is reachable in its first cell and stops
early with a clear error message if it is not.

## Notebook index

| #  | Notebook | Scenario | Time |
|----|----------|----------|------|
| 01 | [`01_hello_memory.ipynb`](01_hello_memory.ipynb) | Initialise components, add a handful of memories, run your first hybrid search. The minimum viable tour. | ~5 min |
| 02 | [`02_index_and_filter.ipynb`](02_index_and_filter.ipynb) | Index a directory of markdown notes, filter by source / tag / namespace, inspect BM25 vs dense scores, and switch to the `kiwipiepy` tokenizer for Korean content. | ~15 min |
| 03 | [`03_agent_memory_patterns.ipynb`](03_agent_memory_patterns.ipynb) | Build episodic + working memory for an agent: sessions, events, scratchpad, and time-based recall. | ~10 min |
| 04 | [`04_search_tuning.ipynb`](04_search_tuning.ipynb) | Compare the same query under different search configurations — BM25-only, dense-only, balanced, with and without the context window. | ~15 min |
| 05 | [`05_langgraph_integration.ipynb`](05_langgraph_integration.ipynb) | Wire `MemtomemStore` into a minimal two-node LangGraph agent that searches memtomem and writes findings back. | ~20 min |

## How these notebooks stay safe

Every notebook follows the same pattern from
[`packages/memtomem/tests/conftest.py`](../../packages/memtomem/tests/conftest.py):

1. Create a `tempfile.TemporaryDirectory()` for both the SQLite database and
   the memory directory.
2. Override `MEMTOMEM_STORAGE__SQLITE_PATH` and `MEMTOMEM_INDEXING__MEMORY_DIRS`
   via environment variables.
3. Monkey-patch `memtomem.config.load_config_overrides` to a no-op so the
   user's real `~/.memtomem/config.json` cannot leak into the notebook's
   configuration.
4. Close components and clean up the temp directory in the final cell.

This means you can run the notebooks as many times as you like without any
impact on an existing memtomem installation on the same machine.

## Next steps

- The [User Guide](../../docs/guides/user-guide.md) covers the full MCP tool
  surface.
- The [Agent Memory Guide](../../docs/guides/agent-memory-guide.md) digs
  deeper into episodic / working / procedural memory patterns.
- [`docs/guides/integrations/langgraph.md`](../../docs/guides/integrations/langgraph.md)
  is the prose companion to notebook 05.
