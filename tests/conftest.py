"""
Injects stub modules for heavy optional dependencies that are not available
in the local test environment (Python 3.9 / no GPU).
Import-level mocks must run before any package that transitively imports them.
"""
import sys
from unittest.mock import MagicMock
import numpy as np

# ------------------------------------------------------------------
# sentence_transformers stub
# ------------------------------------------------------------------
class _FakeModel:
    def encode(self, texts, normalize_embeddings=True, batch_size=32):
        if isinstance(texts, str):
            return np.zeros(384, dtype="float32")
        return np.zeros((len(texts), 384), dtype="float32")

_st_mock = MagicMock()
_st_mock.SentenceTransformer.return_value = _FakeModel()
sys.modules.setdefault("sentence_transformers", _st_mock)

# ------------------------------------------------------------------
# mcp stub (requires Python 3.10+)
# ------------------------------------------------------------------
_mcp_mock = MagicMock()
sys.modules.setdefault("mcp", _mcp_mock)
sys.modules.setdefault("mcp.server", _mcp_mock)
sys.modules.setdefault("mcp.server.stdio", _mcp_mock)
sys.modules.setdefault("mcp.types", _mcp_mock)

# ------------------------------------------------------------------
# fastapi stub — nur für Tests die feed.py/routes importieren
# (FastAPI läuft in Docker; lokal nicht installiert)
# ------------------------------------------------------------------
try:
    import fastapi  # noqa: F401 — bereits installiert, kein Stub nötig
except ModuleNotFoundError:
    from unittest.mock import MagicMock as _MM

    class _HTTPException(Exception):
        """Minimaler HTTPException-Stub der status_code + detail trägt."""
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class _PassthroughRouter:
        """APIRouter-Stub: Dekoratoren geben die originale Funktion unverändert zurück."""
        def __getattr__(self, name):
            # router.get(...), router.post(...), router.delete(...) etc.
            def _decorator(*args, **kwargs):
                # Gibt einen Dekorator zurück der die Funktion unverändert durchlässt
                def _wrap(fn):
                    return fn
                return _wrap
            return _decorator

    class _PassthroughRouterClass:
        """APIRouter-Klasse: Instanziierung gibt PassthroughRouter zurück."""
        def __new__(cls, *args, **kwargs):
            return _PassthroughRouter()

    _fastapi_stub = _MM()
    _fastapi_stub.HTTPException = _HTTPException
    _fastapi_stub.APIRouter = _PassthroughRouterClass
    _fastapi_stub.Query = lambda *a, **kw: None
    sys.modules.setdefault("fastapi", _fastapi_stub)
    sys.modules.setdefault("fastapi.responses", _MM())
    sys.modules.setdefault("fastapi.routing", _MM())
