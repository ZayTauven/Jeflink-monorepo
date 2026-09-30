from datetime import timedelta

import pytest
from django.utils import timezone

from jeflink.accounts import otp_limits
from jeflink.accounts.models import OtpPhoneBlock
from jeflink.accounts.otp_limits import (
    block_phone,
    is_prefix_slowed,
    phone_blocked_until,
    record_sms_sent,
    record_verified,
    record_verify_failure,
    resend_delay,
    reserve_sms,
    unblock_phone,
)
from jeflink.common.errors import DomainError
from jeflink.common.ratelimit import Limit
from jeflink.trust.models import AuditEvent

PHONE = "+221771234567"
# Les tests qui écrivent un audit durable sont transactionnels (voir trust/tests).
durable_db = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)


def reserve(phone=PHONE, **kwargs):
    kwargs.setdefault("region", "SN")
    reserve_sms(phone=phone, **kwargs)


def code_of(exc_info):
    return exc_info.value.code, exc_info.value.status_code


@pytest.mark.django_db
def test_cinq_sms_par_heure_par_numero():
    for _ in range(5):
        reserve()
    with pytest.raises(DomainError) as exc:
        reserve()
    assert code_of(exc) == ("otp_rate_limited", 429)
    assert 1 <= exc.value.extra["retry_after"] <= 3600
    reserve(phone="+221771234568")  # autre numéro : non touché


@pytest.mark.django_db
def test_huit_sms_par_jour(monkeypatch):
    monkeypatch.setattr(otp_limits, "SMS_PHONE_HOUR", Limit("otp:phone_sms_1h", 100, 3600))
    for _ in range(8):
        reserve()
    with pytest.raises(DomainError):
        reserve()


@pytest.mark.django_db
def test_install_id_limite_les_nouveaux_challenges():
    for i in range(10):
        reserve(phone=f"+2217712340{i:02d}", install_id="inst-1")
    with pytest.raises(DomainError):
        reserve(phone="+221771234099", install_id="inst-1")
    # Un renvoi sur un challenge existant ne compte pas pour install_id.
    reserve(phone="+221771234099", install_id="inst-1", new_challenge=False)


@pytest.mark.django_db
def test_bloc_de_mille_numeros(settings):
    settings.SMS_BLOCK_HOURLY_CAP = 3
    for i in range(3):
        reserve(phone=f"+221771234{i:03d}")
    with pytest.raises(DomainError):
        reserve(phone="+221771234999")
    reserve(phone="+221771235000")  # bloc voisin


@pytest.mark.django_db
def test_refus_ne_consomme_rien(settings):
    settings.SMS_BLOCK_HOURLY_CAP = 1
    reserve(phone="+221771234000")
    with pytest.raises(DomainError):
        reserve(phone="+221771234001")
    # Le numéro refusé n'a pas brûlé son quota personnel.
    assert otp_limits.count(otp_limits.SMS_PHONE_HOUR, "+221771234001") == 0


@durable_db
def test_plafond_global_503_et_audit_une_seule_fois(settings):
    settings.SMS_DAILY_CAP = 2
    settings.SMS_DAILY_CAP_BY_REGION = {"SN": 100}
    reserve(phone="+221771234001")
    reserve(phone="+221771234002")
    for phone in ("+221771234003", "+221771234004"):
        with pytest.raises(DomainError) as exc:
            reserve(phone=phone)
        assert code_of(exc) == ("otp_temporarily_unavailable", 503)
    assert AuditEvent.objects.filter(action="system.sms_cap.reached").count() == 1


@durable_db
def test_blocage_apres_dix_echecs_puis_progression():
    for _ in range(9):
        assert record_verify_failure(PHONE) is False
    assert record_verify_failure(PHONE) is True
    until = phone_blocked_until(PHONE)
    assert until is not None
    assert timedelta(minutes=59) < until - timezone.now() <= timedelta(hours=1)
    with pytest.raises(DomainError) as exc:
        reserve()
    assert exc.value.code == "otp_rate_limited"
    reserve(new_challenge=False)  # un renvoi sur un challenge existant reste possible

    levels = [block_phone(PHONE).level for _ in range(6)]
    assert levels == [2, 3, 4, 5, 6, 7]
    block = OtpPhoneBlock.objects.get()
    assert block.blocked_until - timezone.now() <= timedelta(hours=24)
    event = AuditEvent.objects.filter(action="accounts.otp.phone_blocked").first()
    assert "771234567" not in str(event.metadata)


@durable_db
def test_niveau_repart_a_un_apres_une_periode_calme():
    block = block_phone(PHONE)
    OtpPhoneBlock.objects.filter(pk=block.pk).update(
        blocked_until=timezone.now() - timedelta(hours=25)
    )
    assert block_phone(PHONE).level == 1


@durable_db
def test_levee_par_l_ops(user_factory):
    ops = user_factory()
    block_phone(PHONE)
    assert unblock_phone(PHONE, actor=ops, reason_code="support_verified")
    assert phone_blocked_until(PHONE) is None
    reserve()
    assert AuditEvent.objects.filter(action="ops.accounts.otp_unblocked").count() == 1


@pytest.mark.django_db
def test_prefixe_ralenti_si_la_conversion_s_effondre(settings):
    settings.SMS_CONVERSION_MIN_VOLUME = 10
    for _ in range(10):
        record_sms_sent(PHONE)
    record_verified(PHONE)
    assert is_prefix_slowed(PHONE)
    assert resend_delay(PHONE) == 120
    assert resend_delay("+221761234567") == 60  # autre opérateur


@pytest.mark.django_db
def test_prefixe_sain(settings):
    settings.SMS_CONVERSION_MIN_VOLUME = 10
    for _ in range(10):
        record_sms_sent(PHONE)
    for _ in range(5):
        record_verified(PHONE)
    assert not is_prefix_slowed(PHONE)


@pytest.mark.django_db
def test_redis_injoignable_sans_repli_refuse(redis_down):
    with pytest.raises(DomainError) as exc:
        reserve()
    assert code_of(exc) == ("otp_temporarily_unavailable", 503)


@pytest.mark.django_db
def test_redis_injoignable_repli_en_base(redis_down):
    reserve(fallback=lambda phone: (4, 4))
    with pytest.raises(DomainError) as exc:
        reserve(fallback=lambda phone: (5, 5))
    assert exc.value.code == "otp_rate_limited"
    with pytest.raises(DomainError):
        reserve(fallback=lambda phone: (0, 8))


@pytest.mark.django_db
def test_echecs_sans_redis_ne_plantent_pas(redis_down):
    assert record_verify_failure(PHONE) is False
