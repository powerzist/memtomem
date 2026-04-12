"""Tests for LLM-based query expansion."""

from __future__ import annotations

import asyncio

import pytest

from memtomem.config import QueryExpansionConfig
from memtomem.errors import LLMError
from memtomem.search.expansion import expand_query_llm


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class FakeLLM:
    def __init__(self, response: str = "", delay: float = 0.0) -> None:
        self._response = response
        self._delay = delay
        self.calls: list[dict] = []

    async def generate(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._response

    async def close(self) -> None:
        pass


class FailingLLM:
    async def generate(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> str:
        raise LLMError("simulated LLM failure")

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# expand_query_llm
# ---------------------------------------------------------------------------


class TestExpandQueryLlm:
    @pytest.mark.anyio
    async def test_appends_terms(self):
        llm = FakeLLM(response="synonym1, synonym2, synonym3")
        result = await expand_query_llm("original query", llm, max_terms=3)
        assert result.startswith("original query ")
        assert "synonym1" in result

    @pytest.mark.anyio
    async def test_deduplicates_query_words(self):
        llm = FakeLLM(response="original, new_term, query")
        result = await expand_query_llm("original query", llm, max_terms=3)
        # "original" and "query" are already in the query, should not be appended
        parts = result.split()
        assert parts.count("original") == 1
        assert parts.count("query") == 1

    @pytest.mark.anyio
    async def test_respects_max_terms(self):
        llm = FakeLLM(response="a, b, c, d, e")
        result = await expand_query_llm("test", llm, max_terms=2)
        added = result.replace("test ", "").split()
        assert len(added) == 2

    @pytest.mark.anyio
    async def test_empty_response_returns_original(self):
        llm = FakeLLM(response="")
        result = await expand_query_llm("test query", llm)
        assert result == "test query"

    @pytest.mark.anyio
    async def test_strips_code_fence(self):
        llm = FakeLLM(response="```\nterm1, term2\n```")
        result = await expand_query_llm("test", llm)
        assert "term1" in result

    @pytest.mark.anyio
    async def test_llm_error_propagates(self):
        """Caller is responsible for catching — function itself raises."""
        with pytest.raises(LLMError):
            await expand_query_llm("test", FailingLLM())

    @pytest.mark.anyio
    async def test_timeout_raises(self):
        """LLM that exceeds 3s timeout raises TimeoutError."""
        slow_llm = FakeLLM(response="slow answer", delay=5.0)
        with pytest.raises(asyncio.TimeoutError):
            await expand_query_llm("test", slow_llm)


# ---------------------------------------------------------------------------
# QueryExpansionConfig validator
# ---------------------------------------------------------------------------


class TestQueryExpansionConfig:
    def test_llm_strategy_accepted(self):
        config = QueryExpansionConfig(strategy="llm")
        assert config.strategy == "llm"

    def test_invalid_strategy_rejected(self):
        with pytest.raises(ValueError, match="strategy"):
            QueryExpansionConfig(strategy="invalid")
