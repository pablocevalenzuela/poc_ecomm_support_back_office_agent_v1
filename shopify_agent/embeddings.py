"""Embeddings locales para el catálogo RAG.

Sustituye a ``HuggingFaceEndpointEmbeddings``, que llamaba a la API de
inferencia de Hugging Face. Desde 2025 esa API funciona con créditos
prepago (Inference Providers), así que sin saldo devuelve 402 y el flujo RAG
queda inutilizable.

``fastembed`` ejecuta el mismo modelo (``all-MiniLM-L6-v2``) en local vía
ONNX Runtime: mismos 384 dims, sin token, sin cuota y sin coste. El modelo se
descarga una sola vez (~90 MB) y se reutiliza durante toda la vida del proceso.
"""
import asyncio
import logging
from functools import lru_cache
from typing import Iterable, List

from fastembed import TextEmbedding

logger = logging.getLogger("SHOPIFY-EMBEDDINGS")

# Debe coincidir con la dimensión de product_catalog_embeddings.embedding
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def get_embedder() -> TextEmbedding:
    """Carga el modelo ONNX una sola vez por proceso."""
    logger.info(f"Cargando modelo de embeddings local: {EMBEDDING_MODEL}")
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def embed_documents(texts: Iterable[str]) -> List[List[float]]:
    """Vectoriza documentos/fragmentos para la ingesta."""
    return [vector.tolist() for vector in get_embedder().embed(list(texts))]


def embed_query(text: str) -> List[float]:
    """Vectoriza una consulta de búsqueda."""
    return next(iter(get_embedder().query_embed(text))).tolist()


async def aembed_query(text: str) -> List[float]:
    """fastembed es síncrono y usa CPU; lo movemos a un hilo para no bloquear."""
    return await asyncio.to_thread(embed_query, text)
