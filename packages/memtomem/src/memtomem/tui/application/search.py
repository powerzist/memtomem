"""Framework-neutral Search use case for the independent TUI.

This adapter intentionally crosses only the non-CLI runtime boundary:
``RuntimeManager.lease()`` to ``Components.search_pipeline.search()``. It does
not import Click commands, parse rendered output, start a FileWatcher, index
files, or repair missing embeddings.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from memtomem.chunking.markdown import _parse_validity_bound
from memtomem.tui.application.contracts import (
    OperationExitPolicy,
    OperationResult,
    OperationSpec,
    ProgressEvent,
    UserSafeError,
    UserSafeWarning,
)
from memtomem.tui.application.runtime import RuntimeManager, RuntimeManagerClosedError
from memtomem.tui.runtime import load_tui_config_read_only

if TYPE_CHECKING:
    from memtomem.models import Chunk, ContextInfo, SearchResult
    from memtomem.search.pipeline import RetrievalStats
    from memtomem.server.component_factory import Components
    from memtomem.storage.sqlite_backend import SqliteBackend
    from memtomem.tui.application.operations import OperationContext
    from memtomem.tui.runtime import TuiPaths


logger = logging.getLogger(__name__)


def _load_default_top_k(paths: TuiPaths) -> int:
    """Read the effective Search default without running config migrations."""

    return int(load_tui_config_read_only(paths).search.default_top_k)


@dataclass(frozen=True, slots=True)
class SearchPreflight:
    """Read-only disclosure returned before Search can bootstrap its runtime."""

    runtime_started: bool
    setup_required: bool
    requires_consent: bool
    may_initialize_storage: bool
    may_migrate_schema: bool
    auto_index: bool
    auto_build_missing_embeddings: bool
    message: str
    may_migrate_config: bool = False
    may_rewrite_config_file: bool = False
    default_top_k: int | None = None
    readiness_error: UserSafeError | None = None


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Validated user intent for one CLI-parity search invocation."""

    query: str
    top_k: int | None = None
    source_filter: str | None = None
    tag_filter: str | None = None
    namespace: str | None = None
    scope: str | None = None
    as_of: str | None = None
    allow_runtime_initialization: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.query, str):
            raise TypeError("query must be a string")
        if self.top_k is not None and type(self.top_k) is not int:
            raise TypeError("top_k must be an integer")

    @classmethod
    def from_raw(
        cls,
        query: str,
        top_k: str | int | None = None,
        *,
        source_filter: str | None = None,
        tag_filter: str | None = None,
        namespace: str | None = None,
        scope: str | None = None,
        as_of: str | None = None,
        allow_runtime_initialization: bool = False,
    ) -> SearchRequest:
        """Convert Top-K exactly as the CLI does, without a TUI-only range."""

        return cls(
            query=query,
            top_k=None if top_k is None else int(top_k),
            source_filter=source_filter,
            tag_filter=tag_filter,
            namespace=namespace,
            scope=scope,
            as_of=as_of,
            allow_runtime_initialization=allow_runtime_initialization,
        )


@dataclass(frozen=True, slots=True)
class SearchContextChunk:
    """Detached adjacent chunk safe to retain after releasing a runtime lease."""

    chunk_id: str
    source_file: str
    content: str
    heading_hierarchy: tuple[str, ...]
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class SearchContextDetail:
    """Structured context-window data attached by the core search pipeline."""

    window_before: tuple[SearchContextChunk, ...]
    window_after: tuple[SearchContextChunk, ...]
    parent_content: str | None
    parent_heading: str | None
    sibling_count: int
    chunk_position: int
    total_chunks_in_file: int
    context_tier_used: str | None


@dataclass(frozen=True, slots=True)
class SearchResultItem:
    """One complete, presentation-independent result for Main and Details."""

    chunk_id: str
    rank: int
    score: float
    retrieval_source: str
    source_file: str
    content: str
    heading_hierarchy: tuple[str, ...]
    chunk_type: str
    start_line: int
    end_line: int
    language: str
    tags: tuple[str, ...]
    namespace: str
    scope: str
    project_root: str | None
    valid_from_unix: int | None
    valid_to_unix: int | None
    created_at: datetime
    updated_at: datetime
    via_session_summary: bool
    context: SearchContextDetail | None


@dataclass(frozen=True, slots=True)
class SearchStats:
    """Search and readiness counts used by the TUI diagnostic surfaces."""

    bm25_candidates: int
    dense_candidates: int
    fused_total: int
    final_total: int
    hidden_system_namespaces: int
    indexed_chunks: int | None
    dense_chunks: int | None


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """Detached Search response that outlives its runtime generation lease."""

    query: str
    items: tuple[SearchResultItem, ...]
    stats: SearchStats
    project_context_root: str | None


class SearchService:
    """Run a real search through the long-lived TUI runtime."""

    def __init__(
        self,
        runtime: RuntimeManager[Components],
        *,
        cwd_getter: Callable[[], Path] = Path.cwd,
        default_top_k_loader: Callable[[TuiPaths], int] | None = None,
    ) -> None:
        self._runtime = runtime
        self._cwd_getter = cwd_getter
        self._default_top_k_loader = default_top_k_loader or _load_default_top_k

    def preflight(self) -> SearchPreflight:
        """Read effective settings without migrations, runtime startup, or storage access."""

        runtime_started = self._runtime.started
        setup_required = not runtime_started and not self._runtime.paths.config_path.is_file()
        default_top_k: int | None = None
        readiness_error: UserSafeError | None = None
        if not setup_required:
            try:
                default_top_k = self._default_top_k_loader(self._runtime.paths)
            except Exception:
                logger.debug("TUI Search default Top K is unavailable", exc_info=True)
                if not runtime_started:
                    readiness_error = _config_unreadable_error()
        requires_consent = not runtime_started and not setup_required and readiness_error is None
        may_migrate_config = requires_consent and not self._runtime.paths.is_dev
        if setup_required:
            message = (
                "Search setup is required; create a configuration through the setup workflow "
                "before starting Search."
            )
        elif readiness_error is not None:
            message = " ".join(
                part
                for part in (
                    readiness_error.message,
                    readiness_error.recovery_action,
                )
                if part
            )
        elif requires_consent:
            if may_migrate_config:
                message = (
                    "Starting Search may migrate legacy configuration and rewrite config.json, "
                    "then initialize storage or migrate its schema; it will not index files or "
                    "build missing embeddings."
                )
            else:
                message = (
                    "Starting Search loads the runtime and may initialize storage or migrate its "
                    "schema; it will not index files or build missing embeddings."
                )
        else:
            message = (
                "Search runtime is already active; searches will not index files or build "
                "missing embeddings."
            )
        return SearchPreflight(
            runtime_started=runtime_started,
            setup_required=setup_required,
            requires_consent=requires_consent,
            may_initialize_storage=requires_consent,
            may_migrate_schema=requires_consent,
            auto_index=False,
            auto_build_missing_embeddings=False,
            message=message,
            may_migrate_config=may_migrate_config,
            may_rewrite_config_file=may_migrate_config,
            default_top_k=default_top_k,
            readiness_error=readiness_error,
        )

    @staticmethod
    def operation_spec(request: SearchRequest) -> OperationSpec:
        """Declare Phase 4 Search as visible lifecycle work without cancellation."""

        return OperationSpec(
            name="Search memories",
            cancellable=False,
            exit_policy=OperationExitPolicy.WAIT,
            safe_parameters=(
                (
                    "top_k",
                    "configured default" if request.top_k is None else str(request.top_k),
                ),
            ),
        )

    async def execute(
        self,
        request: SearchRequest,
        context: OperationContext | None = None,
    ) -> OperationResult[SearchResponse]:
        """Validate, bootstrap with consent, and run the complete core pipeline."""

        if not self._runtime.started and not self._runtime.paths.config_path.is_file():
            return OperationResult.failed(
                UserSafeError(
                    code="search.setup-required",
                    message="Search requires a memtomem configuration.",
                    recovery_action="Complete the setup workflow before searching.",
                )
            )
        if not self._runtime.started:
            try:
                self._default_top_k_loader(self._runtime.paths)
            except Exception:
                logger.debug("TUI Search configuration is unreadable", exc_info=True)
                return OperationResult.failed(_config_unreadable_error())

        as_of_unix: int | None = None
        as_of = _empty_to_none(request.as_of)
        if as_of is not None:
            as_of_unix = _parse_validity_bound(as_of, upper=False)
            if as_of_unix is None:
                return OperationResult.failed(
                    UserSafeError(
                        code="search.invalid-as-of",
                        message="The As-of value is not a valid date or quarter.",
                        recovery_action="Use YYYY-MM-DD or YYYY-QN, where N is 1 through 4.",
                    )
                )

        if not self._runtime.started and not request.allow_runtime_initialization:
            return OperationResult.failed(
                UserSafeError(
                    code="search.runtime-consent-required",
                    message="Search runtime initialization has not been acknowledged.",
                    recovery_action="Review the Search initialization notice and confirm it.",
                )
            )

        if context is not None:
            phase = "Searching" if self._runtime.started else "Initializing search runtime"
            context.report_progress(ProgressEvent(phase=phase))

        try:
            async with self._runtime.lease() as lease:
                components = lease.components
                project_context_root = _resolve_project_context_root(
                    components.config.indexing.project_memory_dirs,
                    self._cwd_getter,
                )
                if context is not None:
                    context.report_progress(ProgressEvent(phase="Searching"))
                source_filter = _empty_to_none(request.source_filter)
                tag_filter = _empty_to_none(request.tag_filter)
                results, retrieval_stats = await components.search_pipeline.search(
                    request.query,
                    top_k=request.top_k,
                    source_filter=source_filter,
                    tag_filter=tag_filter,
                    namespace=_empty_to_none(request.namespace),
                    as_of_unix=as_of_unix,
                    scope=_empty_to_none(request.scope),
                    project_context_root=project_context_root,
                )
                indexed_chunks, dense_chunks = await _read_coverage(components.storage)
                response = SearchResponse(
                    query=request.query,
                    items=tuple(_detach_result(result) for result in results),
                    stats=SearchStats(
                        bm25_candidates=retrieval_stats.bm25_candidates,
                        dense_candidates=retrieval_stats.dense_candidates,
                        fused_total=retrieval_stats.fused_total,
                        final_total=retrieval_stats.final_total,
                        hidden_system_namespaces=retrieval_stats.hidden_system_ns,
                        indexed_chunks=indexed_chunks,
                        dense_chunks=dense_chunks,
                    ),
                    project_context_root=(
                        str(project_context_root) if project_context_root is not None else None
                    ),
                )
                return _classify_result(
                    response,
                    retrieval_stats=retrieval_stats,
                    enable_bm25=components.config.search.enable_bm25,
                    enable_dense=components.config.search.enable_dense,
                    embedding_broken=components.embedding_broken is not None,
                    blank_query=not request.query.strip(),
                )
        except RuntimeManagerClosedError:
            return OperationResult.failed(
                UserSafeError(
                    code="search.runtime-closed",
                    message="The Search runtime is shutting down.",
                    recovery_action="Restart the TUI before searching again.",
                )
            )
        except Exception:
            logger.exception("TUI Search failed")
            return OperationResult.failed(
                UserSafeError(
                    code="search.failed",
                    message="Search could not be completed.",
                    recovery_action="Review Search readiness and try again.",
                    retryable=True,
                )
            )


def _empty_to_none(value: str | None) -> str | None:
    """Map an empty TUI field to an omitted CLI option without trimming it."""

    return None if value == "" else value


def _config_unreadable_error() -> UserSafeError:
    """Return the stable user-safe error for a blocked Search bootstrap."""

    return UserSafeError(
        code="search.config-unreadable",
        message="Search cannot start because configuration could not be read safely.",
        recovery_action="Review config.json and config.d before trying again.",
        retryable=True,
    )


def _resolve_project_context_root(
    project_memory_dirs: Iterable[str | Path],
    cwd_getter: Callable[[], Path],
) -> Path | None:
    """Apply the existing longest-containing-project rule without MCP imports."""

    try:
        cwd = cwd_getter().resolve()
    except OSError:
        return None
    best_root: Path | None = None
    best_depth = -1
    for directory in project_memory_dirs:
        try:
            resolved = Path(directory).expanduser().resolve()
        except OSError:
            continue
        if resolved.parent.name != ".memtomem":
            continue
        project_root = resolved.parent.parent
        try:
            cwd.relative_to(project_root)
        except ValueError:
            continue
        depth = len(project_root.parts)
        if depth > best_depth:
            best_root = project_root
            best_depth = depth
    return best_root


async def _read_coverage(storage: SqliteBackend) -> tuple[int | None, int | None]:
    """Read readiness counts only; never repair the index or vector coverage."""

    indexed_chunks: int | None = None
    dense_chunks: int | None = None
    try:
        stats = await storage.get_stats()
        indexed_chunks = int(stats["total_chunks"])
    except Exception:
        logger.debug("Search storage counts unavailable", exc_info=True)
    try:
        coverage = await storage.get_dense_coverage()
        dense_chunks = int(coverage["with_dense"])
        if indexed_chunks is None:
            indexed_chunks = int(coverage["total"])
    except Exception:
        logger.debug("Search dense coverage unavailable", exc_info=True)
    return indexed_chunks, dense_chunks


def _classify_result(
    response: SearchResponse,
    *,
    retrieval_stats: RetrievalStats,
    enable_bm25: bool,
    enable_dense: bool,
    embedding_broken: bool,
    blank_query: bool,
) -> OperationResult[SearchResponse]:
    warnings: list[UserSafeWarning] = []
    degraded = False

    indexed = response.stats.indexed_chunks
    dense = response.stats.dense_chunks
    if blank_query:
        # The core pipeline returns before BM25/dense/rerank for every blank
        # query.  With source/tag filters this is its recall-based filter-only
        # mode; without them it is a successful empty result.  Do not reinterpret
        # either path through retriever or embedding readiness.
        if response.stats.hidden_system_namespaces:
            warnings.append(
                UserSafeWarning(
                    code="search.system-namespaces-hidden",
                    message="System namespaces were excluded by the default namespace filter.",
                    recovery_action="Choose an explicit namespace to include those memories.",
                )
            )
        return OperationResult.succeeded(response, warnings=tuple(warnings))

    bm25_failed = enable_bm25 and retrieval_stats.bm25_error is not None
    dense_failed = enable_dense and (
        retrieval_stats.dense_error is not None
        or embedding_broken
        or (indexed is not None and indexed > 0 and dense == 0)
    )
    if bm25_failed:
        degraded = True
        warnings.append(
            UserSafeWarning(
                code="search.bm25-degraded",
                message="Keyword retrieval failed; available retrieval paths were still used.",
                recovery_action="Review storage and FTS readiness before retrying.",
            )
        )
    if retrieval_stats.dense_error is not None:
        degraded = True
        warnings.append(
            UserSafeWarning(
                code="search.dense-degraded",
                message="Dense retrieval failed; available retrieval paths were still used.",
                recovery_action="Review embedding readiness before retrying.",
            )
        )
    if retrieval_stats.rerank_error is not None:
        degraded = True
        warnings.append(
            UserSafeWarning(
                code="search.reranker-degraded",
                message="Reranking failed; results remain in their pre-rerank order.",
                recovery_action="Review reranker readiness before retrying.",
            )
        )
    if enable_dense and embedding_broken:
        degraded = True
        warnings.append(
            UserSafeWarning(
                code="search.embedding-mismatch",
                message="Stored vectors are incompatible with the configured embedding model.",
                recovery_action="Use the dedicated embedding recovery workflow when available.",
            )
        )

    if enable_dense and indexed is not None and dense is not None and dense < indexed:
        degraded = True
        warnings.append(
            UserSafeWarning(
                code="search.dense-coverage-incomplete",
                message="Some indexed chunks have no dense embedding; they were not repaired.",
                recovery_action="Index or repair embeddings through an explicit source workflow.",
            )
        )

    enabled_failures = (1 if enable_bm25 and bm25_failed else 0) + (
        1 if enable_dense and dense_failed else 0
    )
    enabled_retrievers = int(enable_bm25) + int(enable_dense)
    warning_tuple = tuple(warnings)
    if enabled_retrievers == 0:
        return OperationResult.failed(
            UserSafeError(
                code="search.no-retriever",
                message="No search retrieval method is enabled.",
                recovery_action="Enable keyword or dense retrieval in configuration.",
            ),
            warnings=warning_tuple,
        )
    if enabled_failures == enabled_retrievers:
        return OperationResult.failed(
            UserSafeError(
                code="search.retrieval-failed",
                message="Every enabled search retrieval method failed.",
                recovery_action="Review the retrieval warnings and Search readiness.",
                retryable=True,
            ),
            warnings=warning_tuple,
        )
    if indexed == 0:
        return OperationResult.failed(
            UserSafeError(
                code="search.index-empty",
                message="Search storage contains no indexed memory chunks.",
                recovery_action="Index a memory source through the explicit Sources workflow.",
            ),
            warnings=warning_tuple,
        )
    if response.stats.hidden_system_namespaces:
        warnings.append(
            UserSafeWarning(
                code="search.system-namespaces-hidden",
                message="System namespaces were excluded by the default namespace filter.",
                recovery_action="Choose an explicit namespace to include those memories.",
            )
        )
    if degraded:
        return OperationResult.partial(response, warnings=tuple(warnings))
    return OperationResult.succeeded(response, warnings=tuple(warnings))


def _detach_context_chunk(chunk: Chunk) -> SearchContextChunk:
    metadata = chunk.metadata
    return SearchContextChunk(
        chunk_id=str(chunk.id),
        source_file=str(metadata.source_file),
        content=chunk.content,
        heading_hierarchy=tuple(metadata.heading_hierarchy),
        start_line=metadata.start_line,
        end_line=metadata.end_line,
    )


def _detach_context(context: ContextInfo | None) -> SearchContextDetail | None:
    if context is None:
        return None
    return SearchContextDetail(
        window_before=tuple(_detach_context_chunk(chunk) for chunk in context.window_before),
        window_after=tuple(_detach_context_chunk(chunk) for chunk in context.window_after),
        parent_content=context.parent_content,
        parent_heading=context.parent_heading,
        sibling_count=context.sibling_count,
        chunk_position=context.chunk_position,
        total_chunks_in_file=context.total_chunks_in_file,
        context_tier_used=context.context_tier_used,
    )


def _detach_result(result: SearchResult) -> SearchResultItem:
    chunk = result.chunk
    metadata = chunk.metadata
    return SearchResultItem(
        chunk_id=str(chunk.id),
        rank=result.rank,
        score=result.score,
        retrieval_source=result.source,
        source_file=str(metadata.source_file),
        content=chunk.content,
        heading_hierarchy=tuple(metadata.heading_hierarchy),
        chunk_type=str(metadata.chunk_type),
        start_line=metadata.start_line,
        end_line=metadata.end_line,
        language=metadata.language,
        tags=tuple(metadata.tags),
        namespace=metadata.namespace,
        scope=metadata.scope,
        project_root=str(metadata.project_root) if metadata.project_root is not None else None,
        valid_from_unix=metadata.valid_from_unix,
        valid_to_unix=metadata.valid_to_unix,
        created_at=chunk.created_at,
        updated_at=chunk.updated_at,
        via_session_summary=result.via_session_summary,
        context=_detach_context(result.context),
    )
