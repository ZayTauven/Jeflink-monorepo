import pytest


@pytest.fixture(autouse=True)
def _sans_cle_ia(settings):
    """Les tests n'appellent jamais Claude : sans clé, Jef reste en mode guidé (voir test_jef)."""
    settings.ANTHROPIC_API_KEY = ""
