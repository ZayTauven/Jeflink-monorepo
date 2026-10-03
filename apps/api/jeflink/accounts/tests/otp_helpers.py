"""Aides communes aux tests OTP : demande, lecture du code dans la boîte d'envoi du SMS fake."""

import re
import uuid

from django.urls import reverse

from jeflink.notifications.sms.fake import FakeSmsGateway

PHONE = "+221771234567"
INSTALL_A = "6f1c2d3e-4a5b-4c6d-8e7f-0a1b2c3d4e5f"
INSTALL_B = "0b9a8c7d-6e5f-4a3b-9c2d-1e0f9a8b7c6d"


def last_code() -> str:
    return re.search(r"\b(\d{6})\b", FakeSmsGateway.outbox[-1].body).group(1)


def other_code(code: str) -> str:
    return f"{(int(code) + 1) % 10**6:06d}"


def request_code(api_client, phone=PHONE, *, app="client", key=None, **headers):
    payload = {"phone": phone}
    if app is not None:
        payload["app"] = app
    return api_client.post(
        reverse("auth-otp-request"),
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex,
        **headers,
    )


def verify(api_client, challenge, code, *, install_id=INSTALL_A, terms=None, app="client"):
    from django.conf import settings

    return api_client.post(
        reverse("auth-otp-verify"),
        {
            "challenge_id": challenge["challenge_id"],
            "challenge_secret": challenge["challenge_secret"],
            "code": code,
            "terms_version": terms or settings.TERMS_VERSION,
            "device": {"platform": "android", "label": "Samsung A05", "install_id": install_id},
            "app": app,
        },
        format="json",
    )
