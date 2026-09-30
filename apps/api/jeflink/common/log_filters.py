"""Filtre de journalisation : aucun numéro, code ou jeton ne sort dans les logs (règle 8, S14)."""

import logging

from .pii import redact


class PiiRedactingFilter(logging.Filter):
    """Formate le message puis le filtre ; s'installe sur chaque handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # message mal formé : on le laisse au formateur
            return True
        record.msg = redact(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True
