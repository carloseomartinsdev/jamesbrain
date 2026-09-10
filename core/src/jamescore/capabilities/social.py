"""Social capability — cordiality belongs to James, not PKE. Deterministic, no LLM."""

from __future__ import annotations

import random
import re
import unicodedata
from typing import Any

INTENT_GREETING = "GREETING"
INTENT_FAREWELL = "FAREWELL"
INTENT_THANKS = "THANKS"
INTENT_WELLBEING = "WELLBEING"
INTENT_ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
INTENT_APOLOGY = "APOLOGY"
INTENT_SMALL_TALK = "SMALL_TALK"
INTENT_NONE = "NONE"


def _empty(original: str) -> dict[str, Any]:
    return {
        "intent": INTENT_NONE,
        "has_task": True,
        "task_text": original,
        "social_text": "",
        "confidence": "none",
        "original": original,
    }


class SocialCapability:
    def classify(self, raw: str) -> dict[str, Any]:
        original = raw.strip()
        if original == "":
            return _empty(original)
        if self._looks_like_negative(original):
            return _empty(original)
        norm = self._normalize(original)
        split = self._split_social_and_task(norm, original)
        if split is None:
            return _empty(original)
        return {
            "intent": split["intent"],
            "has_task": split["task_text"] != "",
            "task_text": split["task_text"],
            "social_text": split["social_text"],
            "confidence": "high",
            "original": original,
        }

    def is_social_only(self, classified: dict[str, Any]) -> bool:
        return (
            classified.get("intent", INTENT_NONE) != INTENT_NONE
            and not classified.get("has_task")
            and classified.get("confidence") == "high"
        )

    def should_prefix_social(self, classified: dict[str, Any]) -> bool:
        return (
            classified.get("intent", INTENT_NONE) != INTENT_NONE
            and bool(classified.get("has_task"))
            and classified.get("confidence") == "high"
        )

    def compose(self, intent: str, display_name: str | None = None, social_hint: str = "") -> str:
        name = self._safe_name(display_name)
        period = self._greeting_period(social_hint)

        def pick(options: list[str]) -> str:
            return options[random.randint(0, len(options) - 1)]

        if intent == INTENT_GREETING:
            hello = period or "Olá"
            if name is not None:
                return pick(
                    [
                        f"{hello}, {name}. Como posso ajudar?",
                        f"{hello}, {name}.",
                        f"{hello}, {name}. Em que posso ajudar?",
                    ]
                )
            return pick([f"{hello}. Como posso ajudar?", f"{hello}.", f"{hello}. O que você precisa?"])
        if intent == INTENT_FAREWELL:
            if period == "Boa noite":
                return f"Boa noite, {name}." if name is not None else "Boa noite."
            if name is not None:
                return pick([f"Até mais, {name}.", "Até depois.", "Até logo."])
            return pick(["Até mais.", "Até depois.", "Até logo."])
        if intent == INTENT_THANKS:
            return pick(["Por nada.", "Sempre que precisar.", "Disponha."])
        if intent == INTENT_WELLBEING:
            return pick(
                [
                    "Tudo certo por aqui. E com você?",
                    "Funcionando normalmente. Como posso ajudar?",
                    "Tudo em ordem. E você?",
                ]
            )
        if intent == INTENT_ACKNOWLEDGEMENT:
            return pick(["Certo.", "Perfeito.", "Ok."])
        if intent == INTENT_APOLOGY:
            return pick(["Sem problema.", "Tudo certo."])
        if intent == INTENT_SMALL_TALK:
            return pick(["Entendo.", "Certo.", "Ok."])
        return ""

    def compose_prefix(self, intent: str, display_name: str | None = None, social_hint: str = "") -> str:
        name = self._safe_name(display_name)
        period = self._greeting_period(social_hint)
        if intent == INTENT_GREETING:
            hello = period or "Olá"
            return f"{hello}, {name}." if name is not None else f"{hello}."
        if intent == INTENT_THANKS:
            return "Por nada."
        if intent == INTENT_WELLBEING:
            return "Tudo certo por aqui."
        if intent == INTENT_FAREWELL:
            return f"Até mais, {name}." if name is not None else "Até mais."
        if intent == INTENT_ACKNOWLEDGEMENT:
            return "Certo."
        if intent == INTENT_APOLOGY:
            return "Sem problema."
        return ""

    def merge_prefix(self, prefix: str, pke_text: str) -> str:
        prefix = prefix.strip()
        pke_text = pke_text.strip()
        if prefix == "":
            return pke_text
        if pke_text == "":
            return prefix
        if pke_text.lower().startswith(prefix.lower()):
            return pke_text
        return f"{prefix} {pke_text}"

    def _normalize(self, text: str) -> str:
        t = text.strip().lower()
        t = t.replace("\r\n", "\n").replace("\r", "\n")
        t = re.sub(r"\s+", " ", t)
        t = re.sub(r"[!?.…]+$", "", t)
        return t.strip()

    def _looks_like_negative(self, original: str) -> bool:
        n = self._normalize(original)
        if re.search(r"\b(é uma expressão|significa|usado em|usado no|em português)\b", n):
            return True
        if re.search(r"\b(me deu|lhe deu|deu bom dia|disse bom dia|falou bom dia)\b", n):
            return True
        if re.search(r"\b(ontem|anteontem|semana passada)\b", n) and re.search(
            r"\b(bom dia|boa tarde|boa noite|olá|oi)\b", n
        ):
            return True
        if re.search(r"\b(como você está|como vc está|como esta)\b", n) and re.search(
            r"\b(armazen|guard|salv|persist|banco|dados|nome|conhecimento|pke)\b", n
        ):
            return True
        return False

    def _split_social_and_task(self, norm: str, original: str) -> dict[str, str] | None:
        patterns = self._social_patterns()
        for intent, plist in patterns:
            for pattern in plist:
                m = re.search(pattern, norm)
                if not m:
                    continue
                matched = m.group(0)
                rest_norm = re.sub(r"^[,.;:\-\s]+", "", norm[len(matched) :]).strip()
                task_text = self._strip_leading_connectors(self._strip_prefix_from_original(original, matched))
                if rest_norm == "" and intent == INTENT_ACKNOWLEDGEMENT:
                    if re.search(r"\b(obrigad[oa]|valeu|agrade[cç]o)\b", norm):
                        intent = INTENT_THANKS
                if rest_norm != "" and self._is_pure_social_remainder(rest_norm):
                    folded = self._classify_pure_social(rest_norm)
                    if folded is not None:
                        if folded == INTENT_THANKS or intent == INTENT_THANKS:
                            intent = INTENT_THANKS
                        return {"intent": intent, "social_text": original.strip(), "task_text": ""}
                if rest_norm != "" and not self._looks_like_task(rest_norm) and self._looks_like_assertion(rest_norm):
                    return None
                return {
                    "intent": intent,
                    "social_text": original[: max(0, len(original) - len(task_text))].strip(),
                    "task_text": task_text,
                }
        pure = self._classify_pure_social(norm)
        if pure is not None:
            return {"intent": pure, "social_text": original, "task_text": ""}
        return None

    def _looks_like_task(self, rest_norm: str) -> bool:
        if rest_norm.endswith("?") or "?" in rest_norm:
            return True
        if re.search(r"\b(qual|quais|quem|onde|quando|quanto|como|meu|minha|lembre|anote|registre|guarde)\b", rest_norm):
            return True
        if re.search(r"\b(é|eh|sou|chamo|nome|carro|cor|modelo|marca)\b", rest_norm):
            return True
        return False

    def _looks_like_assertion(self, rest_norm: str) -> bool:
        return len(re.split(r"\s+", rest_norm)) >= 4

    def _is_pure_social_remainder(self, rest_norm: str) -> bool:
        return self._classify_pure_social(rest_norm) is not None

    def _classify_pure_social(self, norm: str) -> str | None:
        n = re.sub(r"[!?.…]+$", "", norm.strip()).strip()
        n = re.sub(r"[,\s]+james\.?$", "", n).strip()
        for intent, aliases in self._pure_social_exact().items():
            if n in aliases:
                return intent
        return None

    def _social_patterns(self) -> list[tuple[str, list[str]]]:
        james = r"(?:[,\s]+james)?"
        return [
            (
                INTENT_GREETING,
                [
                    rf"^(?:bom\s+dia|boa\s+tarde|boa\s+noite){james}\b",
                    rf"^(?:ol[áa]|oi|e\s+a[ií]|eae|hey|hi){james}\b",
                ],
            ),
            (
                INTENT_FAREWELL,
                [
                    rf"^(?:at[ée]\s+mais|at[ée]\s+logo|at[ée]\s+depois|at[ée]\s+amanh[ãa]|tchau|falamos\s+depois|flw){james}\b",
                    rf"^(?:boa\s+noite){james}\b",
                ],
            ),
            (INTENT_THANKS, [rf"^(?:muito\s+obrigad[oa]|obrigad[oa]|valeu|agrade[cç]o){james}\b"]),
            (
                INTENT_WELLBEING,
                [
                    rf"^(?:tudo\s+bem|tudo\s+certo(?:\s+por\s+a[ií])?|como\s+(?:voc[eê]|vc)\s+est[áa]|como\s+est[ãa]o\s+as\s+coisas|est[áa]\s+tudo\s+certo(?:\s+por\s+a[ií])?){james}\b"
                ],
            ),
            (INTENT_APOLOGY, [rf"^(?:desculpa|desculpe|foi\s+mal|perd[ãa]o){james}\b"]),
            (INTENT_ACKNOWLEDGEMENT, [rf"^(?:entendi|certo|ok|okay|perfeito|beleza|combinado|show){james}\b"]),
            (
                INTENT_SMALL_TALK,
                [r"^(?:que\s+dia\s+bonito|hoje\s+est[áa]\s+corrido|estou\s+cansado(?:\s+hoje)?)\b"],
            ),
        ]

    def _pure_social_exact(self) -> dict[str, list[str]]:
        return {
            INTENT_GREETING: [
                "bom dia",
                "boa tarde",
                "boa noite",
                "olá",
                "ola",
                "oi",
                "e aí",
                "e ai",
                "eae",
                "hey",
                "hi",
                "bom dia james",
                "boa tarde james",
                "boa noite james",
                "olá james",
                "ola james",
                "oi james",
                "e aí james",
                "e ai james",
            ],
            INTENT_FAREWELL: [
                "até mais",
                "ate mais",
                "até logo",
                "ate logo",
                "até depois",
                "ate depois",
                "até amanhã",
                "ate amanha",
                "tchau",
                "falamos depois",
                "flw",
                "até mais james",
                "tchau james",
                "boa noite james",
            ],
            INTENT_THANKS: [
                "obrigado",
                "obrigada",
                "muito obrigado",
                "muito obrigada",
                "valeu",
                "agradeço",
                "agradeco",
                "obrigado james",
                "obrigada james",
                "valeu james",
            ],
            INTENT_WELLBEING: [
                "tudo bem",
                "tudo bem?",
                "tudo certo",
                "tudo certo por aí",
                "tudo certo por ai",
                "como você está",
                "como voce esta",
                "como vc está",
                "como vc esta",
                "como estão as coisas",
                "como estao as coisas",
                "está tudo certo por aí",
                "esta tudo certo por ai",
            ],
            INTENT_APOLOGY: ["desculpa", "desculpe", "foi mal", "perdão", "perdao"],
            INTENT_ACKNOWLEDGEMENT: ["entendi", "certo", "ok", "okay", "perfeito", "beleza", "combinado"],
            INTENT_SMALL_TALK: [
                "que dia bonito",
                "hoje está corrido",
                "hoje esta corrido",
                "estou cansado",
                "estou cansado hoje",
            ],
        }

    def _strip_prefix_from_original(self, original: str, matched_norm: str) -> str:
        words = re.split(r"\s+", matched_norm.strip())
        if not words:
            return original
        parts = [re.escape(w) for w in words]
        regex = re.compile(r"^\s*" + r"[,\s]+".join(parts), re.IGNORECASE | re.UNICODE)
        out, n = regex.subn("", original, count=1)
        return out.strip() if n else original.strip()

    def _strip_leading_connectors(self, text: str) -> str:
        t = re.sub(r"^[,.;:!\?\-\s]+", "", text.strip())
        t = re.sub(r"[,.;:!\?\-\s]+$", "", t).strip()
        if t != "" and not any(ch.isalnum() for ch in t):
            return ""
        return t

    def _greeting_period(self, hint: str) -> str | None:
        n = self._normalize(hint)
        if re.search(r"\bbom\s+dia\b", n):
            return "Bom dia"
        if re.search(r"\bboa\s+tarde\b", n):
            return "Boa tarde"
        if re.search(r"\bboa\s+noite\b", n):
            return "Boa noite"
        return None

    def _safe_name(self, display_name: str | None) -> str | None:
        if display_name is None:
            return None
        n = display_name.strip()
        if n == "" or len(n) > 40:
            return None
        if not n[0].isalpha():
            return None
        for ch in n[1:]:
            if not (ch.isalpha() or ch in "'- " or unicodedata.category(ch) == "Mn"):
                return None
        lower = n.lower()
        if lower in {"james", "usuário", "usuario", "user", "admin"}:
            return None
        return n
