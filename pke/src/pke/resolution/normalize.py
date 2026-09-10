"""Normalização lexical previsível. Não é fuzzy matching."""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+", flags=re.UNICODE)


def normalize_lexical(text: str) -> str:
    """casefold + acentos + pontuação irrelevante + espaços colapsados."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = _NON_ALNUM.sub(" ", without_marks)
    return _WS.sub(" ", stripped).strip().casefold()
