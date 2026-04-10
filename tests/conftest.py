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
