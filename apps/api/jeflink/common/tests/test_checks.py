"""Contrôles de déploiement du Redis d'auth (infra 2)."""

import redis

from jeflink.common import checks


def ids(errors):
    return [e.id for e in errors]


def test_url_sans_mot_de_passe_ni_tls(settings):
    settings.RATELIMIT_REDIS_URL = "redis://redis-auth:6379/0"
    settings.AUTH_REDIS_PRIVATE_HOSTS = []
    assert ids(checks.auth_redis_url(None)) == ["common.E201", "common.E202"]


def test_reseau_prive_declare_ou_tls(settings):
    settings.RATELIMIT_REDIS_URL = "redis://:motdepasse@redis-auth:6379/0"
    settings.AUTH_REDIS_PRIVATE_HOSTS = ["redis-auth"]
    assert checks.auth_redis_url(None) == []
    settings.RATELIMIT_REDIS_URL = "rediss://:motdepasse@redis.example.net:6380/0"
    settings.AUTH_REDIS_PRIVATE_HOSTS = []
    assert checks.auth_redis_url(None) == []


class FakeClient:
    def __init__(self, policy=None, error=None):
        self.policy, self.error = policy, error

    def config_get(self, name):
        if self.error:
            raise self.error
        return {name: self.policy}


def test_politique_d_eviction(monkeypatch):
    from jeflink.common import ratelimit

    monkeypatch.setattr(ratelimit, "client", lambda: FakeClient("allkeys-lru"))
    assert ids(checks.auth_redis_policy(None)) == ["common.E205"]
    monkeypatch.setattr(ratelimit, "client", lambda: FakeClient("noeviction"))
    assert checks.auth_redis_policy(None) == []
    monkeypatch.setattr(ratelimit, "client", lambda: FakeClient(error=redis.ResponseError("x")))
    assert ids(checks.auth_redis_policy(None)) == ["common.W203"]
    monkeypatch.setattr(ratelimit, "client", lambda: FakeClient(error=redis.ConnectionError("x")))
    assert ids(checks.auth_redis_policy(None)) == ["common.E204"]
