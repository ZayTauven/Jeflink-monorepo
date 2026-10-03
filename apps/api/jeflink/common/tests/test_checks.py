"""Contrôles de déploiement (infra 2 et 4)."""

import redis

from jeflink.common import checks

STRONG = "motdepasse-redis-auth-tres-long-0123456789abcdef"


def ids(errors):
    return [e.id for e in errors]


def test_url_sans_mot_de_passe_ni_tls(settings):
    settings.RATELIMIT_REDIS_URL = "redis://redis-auth:6379/0"
    settings.AUTH_REDIS_PRIVATE_HOSTS = []
    assert ids(checks.auth_redis_url(None)) == ["common.E201", "common.E202"]


def test_mot_de_passe_court_ou_de_dev(settings):
    settings.AUTH_REDIS_PRIVATE_HOSTS = ["redis-auth"]
    for password in ("court", "local-dev-redis-auth-not-secret-xxxxxxxxxxxxxxx"):
        settings.RATELIMIT_REDIS_URL = f"redis://:{password}@redis-auth:6379/0"
        assert ids(checks.auth_redis_url(None)) == ["common.E201"]


def test_reseau_prive_declare_ou_tls(settings):
    settings.RATELIMIT_REDIS_URL = f"redis://:{STRONG}@redis-auth:6379/0"
    settings.AUTH_REDIS_PRIVATE_HOSTS = ["redis-auth"]
    assert checks.auth_redis_url(None) == []
    settings.RATELIMIT_REDIS_URL = f"rediss://:{STRONG}@redis.example.net:6380/0"
    settings.AUTH_REDIS_PRIVATE_HOSTS = []
    assert checks.auth_redis_url(None) == []


def test_tls_sans_verification_refuse(settings):
    settings.AUTH_REDIS_PRIVATE_HOSTS = []
    settings.RATELIMIT_REDIS_URL = f"rediss://:{STRONG}@redis.example.net:6380/0?ssl_cert_reqs=none"
    assert ids(checks.auth_redis_url(None)) == ["common.E206"]


class FakeClient:
    def __init__(self, info=None, config=None, error=None):
        self._info, self._config, self.error = info, config, error

    def info(self, section):
        if self.error:
            raise self.error
        if isinstance(self._info, Exception):
            raise self._info
        return {"maxmemory_policy": self._info} if self._info else {}

    def config_get(self, name):
        if isinstance(self._config, Exception):
            raise self._config
        return {name: self._config}


def test_politique_lue_par_info_puis_config(monkeypatch, settings):
    from jeflink.common import ratelimit

    settings.AUTH_REDIS_NOEVICTION_ATTESTED = False
    cases = [
        (FakeClient(info="allkeys-lru"), ["common.E205"]),
        (FakeClient(info="noeviction"), []),
        (FakeClient(info=redis.ResponseError("x"), config="noeviction"), []),
        (
            FakeClient(info=redis.ResponseError("x"), config=redis.ResponseError("x")),
            ["common.E203"],
        ),
        (FakeClient(error=redis.ConnectionError("x")), ["common.E204"]),
    ]
    for fake, expected in cases:
        monkeypatch.setattr(ratelimit, "client", lambda fake=fake: fake)
        assert ids(checks.auth_redis_policy(None)) == expected


def test_politique_illisible_mais_attestee(monkeypatch, settings):
    from jeflink.common import ratelimit

    settings.AUTH_REDIS_NOEVICTION_ATTESTED = True
    fake = FakeClient(info=redis.ResponseError("x"), config=redis.ResponseError("x"))
    monkeypatch.setattr(ratelimit, "client", lambda: fake)
    assert checks.auth_redis_policy(None) == []


def test_proxies_de_confiance(settings):
    settings.BFF_TRUSTED_NETWORKS = ["10.20.0.0/24"]
    settings.FORWARDED_ALLOW_IPS = ["10.10.0.5", "10.10.0.6"]
    assert checks.trusted_proxies(None) == []
    for value, expected in (
        (["0.0.0.0/0"], ["common.E302", "common.E304"]),
        (["10.0.0.0/8"], ["common.E302", "common.E304"]),
        (["::/0"], ["common.E302"]),
        (["10.20.0.9"], ["common.E304"]),
        (["pas-une-ip"], ["common.E301"]),
        ([], ["common.E303"]),
    ):
        settings.FORWARDED_ALLOW_IPS = value
        assert ids(checks.trusted_proxies(None)) == expected, value


def test_x_forwarded_host_interdit(settings):
    settings.BFF_TRUSTED_NETWORKS = []
    settings.FORWARDED_ALLOW_IPS = ["10.10.0.5"]
    settings.USE_X_FORWARDED_HOST = True
    assert ids(checks.trusted_proxies(None)) == ["common.E305"]
