class AuditConnectionRouter:
    """La connexion « audit » vise la même base que « default » : jamais de migration par elle."""

    def allow_migrate(self, db: str, app_label: str, **hints) -> bool | None:
        return False if db == "audit" else None
