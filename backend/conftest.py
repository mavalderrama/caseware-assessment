"""
Session-level test configuration.

Patches `sentence_transformers` in sys.modules *before* Django initialises so
that AppConfig.ready() → rebuild_from_lake() → _get_model() never loads the
real ~400 MB SentenceTransformer model during test runs.

The mock encode() returns a list of row-mocks whose .tolist() produces a
384-dimensional zero vector, which satisfies every call site in the codebase:

    embeddings = model.encode(texts, normalize_embeddings=True)
    for emb in embeddings:          # iterable ✓
        emb.tolist()                # .tolist() ✓
    query_vec = embeddings[0]       # index access ✓
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _make_row_mock() -> MagicMock:
    row = MagicMock()
    row.tolist.return_value = [0.0] * 384
    return row


def _mock_encode(texts: list[str], **kwargs: object) -> list[MagicMock]:
    return [_make_row_mock() for _ in texts]


_mock_model = MagicMock()
_mock_model.encode.side_effect = _mock_encode

_mock_st_module = MagicMock()
_mock_st_module.SentenceTransformer.return_value = _mock_model

sys.modules["sentence_transformers"] = _mock_st_module
