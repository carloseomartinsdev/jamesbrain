"""Erros do OntologyRegistry."""


class OntologyError(Exception):
    """Falha de registry ontológico."""


class ConceptNotFoundError(OntologyError):
    def __init__(self, token: str) -> None:
        self.token = token
        super().__init__(f"conceito inexistente: {token}")


class ConceptConflictError(OntologyError):
    """Key duplicada ou divergência key × concept_id."""


class ConceptKindError(OntologyError):
    """Kind incompatível com o exigido pelo chamador."""


class CoreMutationError(OntologyError):
    """Tentativa de criar, alterar ou substituir conceito CORE em runtime."""
