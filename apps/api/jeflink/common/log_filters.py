"""Filtre de journalisation : aucun numéro, code ou jeton ne sort dans les logs (règle 8, S14)."""

import logging

from .pii import redact


class PiiRedactingFilter(logging.Filter):
    """Formate le message puis le filtre ; s'installe sur chaque handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            # Arguments incohérents : on filtre le tout plutôt que de laisser le handler
            # recopier record.args en clair sur stderr (M6).
            message = f"{record.msg!r} {record.args!r}"
        record.msg = redact(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True
