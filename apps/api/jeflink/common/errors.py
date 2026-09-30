"""Erreurs métier : un code stable que les fronts traduisent (``ApiError.code`` côté TS)."""

from typing import Any


class DomainError(Exception):
    """Erreur métier. Le message n'est jamais montré : seul ``code`` (et ``extra``) sort de l'API.

    ``extra`` ne contient jamais la saisie de l'utilisateur (spec 001 S14).
    """

    status_code = 400

    def __init__(self, code: str, *, status: int | None = None, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.extra = extra
        if status is not None:
            self.status_code = status
