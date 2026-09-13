"""Reject presenter output that invents facts, flips epistemic status, or leaks internals."""

from __future__ import annotations

import re
import unicodedata

from jamescore.presentation.contract import PresenterInput

_MAX_CHARS = 420
_IMPLEMENTATION = re.compile(
    r"\b(persistido|persistida|banco de dados|consulta|entidade|materializado|"
    r"materializada|canonical|pke|registrado|registrada|registro|query|entity)\b",
    re.I,
)
_FALSE_ONLY = re.compile(r"^\s*(não|nao|no)\.?\s*$", re.I)
_UNKNOWN = re.compile(
    r"\b(ainda não sei|ainda nao sei|não sei|nao sei|i (?:do not|don't) know|"
    r"aún no sé|aun no se|no sé|no se)\b",
    re.I,
)
_FACTUAL_NO = re.compile(
    r"\b(você não tem|voce nao tem|you don't have|you do not have|"
    r"no tienes|não, você não|nao, voce nao|pelo que sei,\s*não|"
    r"pelo que sei,\s*nao)\b",
    re.I,
)
_ERROR_OK = re.compile(
    r"\b(não consegui|nao consegui|consultar|agora|indisponível|indisponivel|"
    r"couldn't|could not|right now|ahora)\b",
    re.I,
)
_STOP = {
    "a", "ao", "aos", "as", "à", "às", "o", "os", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "por", "para",
    "com", "sem", "e", "é", "ou", "que", "se", "seu", "sua", "seus", "suas",
    "meu", "minha", "meus", "minhas", "teu", "tua", "dele", "dela", "deles", "delas",
    "você", "voce", "vocês", "voces", "eu", "tu", "ele", "ela", "nós", "nos",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "was", "were", "be", "been", "it", "its", "her", "his", "your", "you", "my",
    "name", "nome", "sim", "não", "nao", "yes", "no", "ainda", "sei", "pelo",
    "que", "isso", "essa", "esse", "isto", "aqui", "como", "qual", "what",
    "have", "has", "tem", "tenho", "chamada", "chama", "called", "llama",
    "se", "llamo", "llaman", "color", "cor", "azul", "cat", "gato", "gata",
    "carro", "car", "bicicleta", "bike", "ainda", "vou", "lembrar", "entendi",
    "certo", "ok", "bem", "pois", "então", "entao", "já", "ja", "não",
    "el", "la", "los", "las", "un", "una", "su", "tus", "mi", "mis",
}


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).casefold()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9áéíóúãõçñü]+", _fold(text), re.I)


def attested_tokens(inp: PresenterInput) -> set[str]:
    chunks = [inp.user_message, inp.result.status, inp.result.kind or "", inp.result.reason or ""]
    chunks.extend(inp.result.values)
    chunks.extend(inp.result.matched_entities)
    chunks.extend(inp.result.candidates)
    if inp.result.value is not None:
        chunks.append(inp.result.value)
    if inp.result.dimension:
        chunks.append(inp.result.dimension)
    if inp.result.unit:
        chunks.append(inp.result.unit)
    if inp.result.entity:
        for key in ("name", "canonical_name", "label"):
            if inp.result.entity.get(key):
                chunks.append(str(inp.result.entity[key]))
    for item in inp.result.items:
        for key in ("label", "value", "unit"):
            if item.get(key) is not None:
                chunks.append(str(item[key]))
    for turn in inp.conversation_context:
        chunks.append(turn.text)
    attested: set[str] = set(_STOP)
    for chunk in chunks:
        attested.update(_tokens(str(chunk)))
    return attested


def required_values(inp: PresenterInput) -> list[str]:
    result = inp.result
    if result.status in {"no_results", "unknown", "error", "unsupported", "insufficient"}:
        return []
    if result.status == "needs_clarification":
        return list(result.candidates)
    names = [name for name in result.matched_entities if name.strip()]
    skip = {"yes", "no", "unknown", "true", "false"}
    values: list[str] = []
    for value in result.values:
        folded = value.strip().casefold()
        if folded not in skip:
            values.append(value)
    if result.kind in {"measurement", "attribute", "state", "intrinsic_property"}:
        ordered: list[str] = []
        for item in names + values:
            if item not in ordered:
                ordered.append(item)
        return ordered
    if names:
        return names
    return values


def _contains_all(text: str, values: list[str]) -> bool:
    folded = _fold(text)
    for value in values:
        if _fold(value) not in folded:
            return False
    return True


def unattested_content_tokens(text: str, attested: set[str]) -> list[str]:
    extra: list[str] = []
    for token in _tokens(text):
        if len(token) < 4:
            continue
        if token.isdigit():
            extra.append(token)
            continue
        if token not in attested:
            extra.append(token)
    return extra


def validate_presenter_text(text: str, inp: PresenterInput) -> str | None:
    """Return a reason if the reply must be discarded; None if acceptable."""
    reply = (text or "").strip()
    if not reply:
        return "empty"
    if len(reply) > _MAX_CHARS:
        return "too_long"
    if reply.startswith("{") or reply.startswith("```"):
        return "malformed"
    status = inp.result.status
    if not inp.technical_question and _IMPLEMENTATION.search(reply):
        return "implementation_term"
    required = required_values(inp)
    if required and not _contains_all(reply, required):
        return "missing_value"
    if status == "no_results":
        if _FALSE_ONLY.match(reply) or (_FACTUAL_NO.search(reply) and not _UNKNOWN.search(reply)):
            return "no_results_as_false"
        if not _UNKNOWN.search(reply):
            return "no_results_missing_unknown"
    if status == "answered" and inp.result.relation_answer is False:
        if _UNKNOWN.search(reply) and not _FACTUAL_NO.search(reply) and not _FALSE_ONLY.match(reply):
            return "false_as_unknown"
        if _UNKNOWN.search(reply) and "ainda" in _fold(reply):
            return "false_as_unknown"
    if status == "error":
        if _UNKNOWN.search(reply) and not _ERROR_OK.search(reply):
            return "error_as_unknown"
        if not _ERROR_OK.search(reply):
            return "error_not_failure"
    extra = unattested_content_tokens(reply, attested_tokens(inp))
    if status in {"answered", "committed", "no_results", "needs_clarification"} and len(extra) >= 3:
        return "unattested_facts"
    if status == "answered" and extra:
        invented = [token for token in extra if token not in _STOP]
        if any(token.isdigit() for token in invented):
            return "unattested_facts"
        if any(token in {"siamesa", "siames", "anos", "years", "year"} for token in invented):
            return "unattested_facts"
    return None
