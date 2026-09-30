import os

# Les tests tournent dans le conteneur api (PostGIS et Redis réels) ; valeurs factices ailleurs.
_TEST_ENV = {
    "DJANGO_ENV": "test",
    "SECRET_KEY": "test-secret-key-not-used-anywhere-else-0000",
    "REDIS_URL": "redis://redis:6379/15",
    "REDIS_CACHE_URL": "redis://redis:6379/14",
    "JWT_SIGNING_KEYS": (
        "t1:test-jwt-key-one-aaaaaaaaaaaaaaaaaaaaaaaa,t2:test-jwt-key-two-bbbbbbbbbbbbbbbbbbbbbbbb"
    ),
    "OTP_HMAC_KEY": "test-otp-hmac-key-cccccccccccccccccccccccc",
    "MFA_ENCRYPTION_KEYS": "dGVzdC1tZmEtZmVybmV0LWtleS0wMDAwMDAwMDAwMDA=",
    "BFF_SHARED_SECRETS": "test-bff-secret-eeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "PII_HMAC_KEY": "test-pii-hmac-key-ffffffffffffffffffffffffff",
}
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)

from .base import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
PAYMENT_GATEWAY = "fake"
