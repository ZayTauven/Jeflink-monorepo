import time

import pytest

from jeflink.common.ratelimit import (
    Limit,
    RateLimitUnavailable,
    client,
    consume,
    count,
    reset,
)

A = Limit("test:a", 3, 60)
B = Limit("test:b", 1, 60)


def test_autorise_jusqu_a_la_limite_puis_refuse():
    for _ in range(3):
        assert consume([(A, "x")]).allowed
    refus = consume([(A, "x")])
    assert not refus.allowed
    assert refus.exceeded == "test:a"
    assert 1 <= refus.retry_after <= 60
    assert count(A, "x") == 3


def test_identites_separees():
    for _ in range(3):
        consume([(A, "x")])
    assert consume([(A, "y")]).allowed


def test_tout_ou_rien():
    assert consume([(A, "x"), (B, "x")]).allowed
    refus = consume([(A, "x"), (B, "x")])
    assert refus.exceeded == "test:b"
    # La limite A n'a pas été consommée par l'appel refusé.
    assert count(A, "x") == 1


def test_fenetre_glissante():
    court = Limit("test:court", 1, 1)
    assert consume([(court, "x")]).allowed
    assert not consume([(court, "x")]).allowed
    time.sleep(1.1)
    assert consume([(court, "x")]).allowed


def test_reset():
    consume([(B, "x")])
    reset(B, "x")
    assert consume([(B, "x")]).allowed


def test_aucune_identite_en_clair_dans_redis():
    consume([(A, "+221771234567")])
    keys = [k.decode() for k in client().keys("*")]
    assert keys
    assert all("771234567" not in k for k in keys)


def test_redis_injoignable(redis_down):
    with pytest.raises(RateLimitUnavailable):
        consume([(A, "x")])
    with pytest.raises(RateLimitUnavailable):
        count(A, "x")
