"""
Singleton embedding model — geladen einmalig beim ersten Aufruf.
Mehrsprachiges Modell: DE, EN, FR, IT und 50+ weitere Sprachen.
"""
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from swiss_truth_mcp.config import settings


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


async def embed_text(text: str) -> list[float]:
    model = _get_model()
    # SentenceTransformer.encode ist synchron — für PoC ausreichend
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [e.tolist() for e in embeddings]
