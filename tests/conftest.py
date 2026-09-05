import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import fetch_sources  # noqa: E402


def _have(key: str) -> bool:
    return fetch_sources.path_of(key).exists()


requires_book = pytest.mark.skipif(
    not _have("pg64976"),
    reason="data/raw/pg64976.txt が未取得(python pipeline/fetch_sources.py)",
)

requires_lexicon = pytest.mark.skipif(
    not (_have("fr_words") and _have("fr_words_alt")),
    reason="現代フランス語の語彙集が未取得(python pipeline/fetch_sources.py)",
)
