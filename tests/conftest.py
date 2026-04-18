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
    # FastAPI class stub — returns a minimal object with include_router, mount, add_middleware
    _fastapi_stub.FastAPI = _MM
    sys.modules.setdefault("fastapi", _fastapi_stub)
    sys.modules.setdefault("fastapi.responses", _MM())
    sys.modules.setdefault("fastapi.routing", _MM())
    sys.modules.setdefault("fastapi.requests", _MM())
    sys.modules.setdefault("fastapi.staticfiles", _MM())
    sys.modules.setdefault("fastapi.templating", _MM())
    sys.modules.setdefault("starlette.types", _MM())

# ------------------------------------------------------------------
# uvicorn stub — api/main.py importiert uvicorn für den main()-Einstiegspunkt
# ------------------------------------------------------------------
try:
    import uvicorn  # noqa: F401
except ModuleNotFoundError:
    from unittest.mock import MagicMock as _UMM
    _uvicorn_stub = _UMM()
    sys.modules.setdefault("uvicorn", _uvicorn_stub)

# ------------------------------------------------------------------
# api/main.py-Abhängigkeiten stubben damit lifespan-Tests importieren können
# (api/models.py nutzt float|None Union-Syntax die Python 3.9 nicht versteht)
# ------------------------------------------------------------------
from unittest.mock import MagicMock as _RMM
sys.modules.setdefault("starlette", _RMM())
sys.modules.setdefault("starlette.types", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.models", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.claims", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.search", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.review", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.n8n", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.dashboard", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.auth", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.users", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.generate", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.anchor", _RMM())
sys.modules.setdefault("swiss_truth_mcp.api.routes.kanban", _RMM())
sys.modules.setdefault("swiss_truth_mcp.middleware.rate_limiter", _RMM())
sys.modules.setdefault("swiss_truth_mcp.mcp_server.http_server", _RMM())
