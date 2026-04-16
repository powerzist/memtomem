"""Embedder factory: instantiates the right EmbeddingProvider from config."""

from __future__ import annotations

from typing import TYPE_CHECKING

from memtomem.config import EmbeddingConfig
from memtomem.errors import ConfigError

if TYPE_CHECKING:
    from memtomem.embedding.base import EmbeddingProvider


def create_embedder(config: EmbeddingConfig) -> EmbeddingProvider:
    """Return the embedding provider for the configured provider name."""
    provider = config.provider.lower()

    if provider == "none":
        from memtomem.embedding.noop import NoopEmbedder

        return NoopEmbedder()

    if provider == "onnx":
        from memtomem.embedding.onnx import OnnxEmbedder

        return OnnxEmbedder(config)

    if provider == "ollama":
        from memtomem.embedding.ollama import OllamaEmbedder

        return OllamaEmbedder(config)

    if provider == "openai":
        from memtomem.embedding.openai import OpenAIEmbedder

        return OpenAIEmbedder(config)

    raise ConfigError(
        f"Unknown embedding provider: {config.provider!r}. Supported: none, onnx, ollama, openai"
    )
