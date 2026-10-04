from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.utils import timezone

from jeflink.analytics.models import UnservedDemand
from jeflink.catalog.models import Trade
from jeflink.catalog.tests.factories import ServiceFactory, TradeFactory
from jeflink.common.errors import DomainError
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests import services
from jeflink.requests.drafts import RequestDraft
from jeflink.requests.models import ServiceRequest
from jeflink.requests.selectors import eligible_providers
from jeflink.trust.models import AuditEvent
from jeflink.zones.tests.factories import ZoneFactory

from .factories import ServiceRequestFactory

pytestmark = pytest.mark.django_db

KEY = "k" * 30
OUAKAM = Point(-17.4900, 14.7250, srid=4326)


@pytest.fixture
def scene():
    trade = TradeFactory(slug="plomberie")
    service = ServiceFactory(trade=trade, slug="fuite", urgent=True)
    zone = ZoneFactory(slug="ouakam", name="Ouakam", trades=[trade], aliases=["ouakam"])
    zone.center = OUAKAM
    zone.save()
    pro = VerifiedProviderFactory(trades=[trade], zones=[zone])
    return {"trade": trade, "service": service, "zone": zone, "pro": pro}


def draft(**overrides) -> RequestDraft:
    base = {
        "trade_slug": "plomberie",
        "zone_slug": "ouakam",
        "landmark": "près de la boutique, portail bleu",
        "description": "Fuite sous l'évier",
    }
    return RequestDraft(**{**base, **overrides})


def create(client, d=None, *, key=KEY, channel="web"):
    return services.create_request(
        client=client, draft=d or draft(), channel=channel, idempotency_key=key
    )


def refused(client, d, code, key=KEY):
    with pytest.raises(DomainError) as exc:
        create(client, d, key=key)
    assert exc.value.code == code
    return exc.value


def test_creation_par_slug_ouvre_la_demande(complete_user_factory, scene):
    client = complete_user_factory()
    before = timezone.now()
    result = create(client)
    request = result.request
    assert result.created
    assert request.status == ServiceRequest.Status.OPEN
    assert request.zone == scene["zone"] and request.client == client
    assert request.expires_at - before == pytest.approx(
        timedelta(hours=72), abs=timedelta(minutes=1)
    )
    assert request.landmark and request.zone_text == ""


def test_urgence_par_defaut_celle_du_service_et_echeance_24h(complete_user_factory, scene):
    result = create(complete_user_factory(), draft(service_slug="fuite", description=""))
    request = result.request
    assert request.urgent and request.service == scene["service"]
    delta = request.expires_at - timezone.now()
    assert timedelta(hours=23) < delta <= timedelta(hours=24)


def test_urgence_explicite_prime_sur_le_service(complete_user_factory, scene):
    request = create(complete_user_factory(), draft(service_slug="fuite", urgent=False)).request
    assert not request.urgent


def test_zone_par_texte_libre(complete_user_factory, scene):
    request = create(complete_user_factory(), draft(zone_slug=None, zone_text="Ouakam")).request
    assert request.zone == scene["zone"] and request.status == "open"


def test_zone_par_position_avec_repere_facultatif(complete_user_factory, scene):
    d = draft(zone_slug=None, landmark="", location=OUAKAM)
    request = create(complete_user_factory(), d).request
    assert request.zone == scene["zone"] and request.location is not None
    assert request.landmark == ""


def test_quartier_inconnu_passe_en_needs_zone_sans_echeance(complete_user_factory, scene):
    d = draft(zone_slug=None, zone_text="Keur Massar 2")
    request = create(complete_user_factory(), d).request
    assert request.status == ServiceRequest.Status.NEEDS_ZONE
    assert request.zone is None and request.expires_at is None
    assert request.zone_text == "keur massar"
    signal = UnservedDemand.objects.get(reason="zone_unknown")
    assert signal.zone_text == "keur massar" and signal.trade_slug == "plomberie"


def test_zone_ambigue_ne_cree_rien_puis_rejeu_avec_le_slug_choisi(complete_user_factory, scene):
    other = ZoneFactory(slug="ngor", name="Ngor", trades=[scene["trade"]])
    other.center = OUAKAM
    other.save()
    client = complete_user_factory()
    d = draft(zone_slug=None, landmark="", location=OUAKAM)
    error = refused(client, d, "zone_ambiguous")
    assert {c["slug"] for c in error.extra["candidates"]} == {"ouakam", "ngor"}
    assert not ServiceRequest.objects.exists() and not UnservedDemand.objects.exists()
    # Même clé : rejouée avec le zone_slug choisi, elle réussit.
    result = create(client, draft(zone_slug="ngor", landmark="", location=OUAKAM))
    assert result.created and result.request.zone == other


def test_metier_non_ouvert_dans_la_zone_refuse_et_signale(complete_user_factory, scene):
    TradeFactory(slug="electricite")
    refused(complete_user_factory(), draft(trade_slug="electricite"), "trade_not_in_zone")
    signal = UnservedDemand.objects.get()
    assert (signal.reason, signal.trade_slug, signal.zone_slug) == (
        "trade_not_in_zone",
        "electricite",
        "ouakam",
    )
    assert not ServiceRequest.objects.exists()


def test_hors_zone_refuse_et_signale_sans_le_point(complete_user_factory, scene):
    far = Point(-16.0, 14.0, srid=4326)
    refused(
        complete_user_factory(), draft(zone_slug=None, landmark="", location=far), "out_of_area"
    )
    signal = UnservedDemand.objects.get()
    assert signal.reason == "out_of_area" and signal.nearest_zone_slug == "ouakam"
    assert signal.distance_km is not None and signal.distance_km > 10


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"trade_slug": "inconnu"}, "trade_not_found"),
        ({"zone_slug": "inconnue"}, "zone_not_found"),
    ],
)
def test_metier_ou_zone_inconnus(complete_user_factory, scene, overrides, code):
    refused(complete_user_factory(), draft(**overrides), code)
    assert UnservedDemand.objects.get().reason == code


def test_metier_et_zone_inactifs(complete_user_factory, scene):
    scene["trade"].is_active = False
    scene["trade"].save()
    refused(complete_user_factory(), draft(), "trade_inactive")
    scene["trade"].is_active = True
    scene["trade"].save()
    scene["zone"].is_active = False
    scene["zone"].save()
    refused(complete_user_factory(), draft(), "zone_inactive", key="z" * 30)


def test_service_d_un_autre_metier_refuse(complete_user_factory, scene):
    other = ServiceFactory(slug="panne")
    assert other.trade_id != scene["trade"].pk
    refused(complete_user_factory(), draft(service_slug="panne"), "service_not_in_trade")
    refused(complete_user_factory(), draft(service_slug="absent"), "service_not_in_trade")


def test_description_obligatoire_sans_service(complete_user_factory, scene):
    refused(complete_user_factory(), draft(description="ab"), "description_required")
    refused(complete_user_factory(), draft(description="   "), "description_required")
    # Avec un service, elle devient facultative.
    assert create(complete_user_factory(), draft(service_slug="fuite", description="")).created


def test_repere_ou_position_obligatoire(complete_user_factory, scene):
    refused(complete_user_factory(), draft(landmark="  "), "landmark_or_location_required")


def test_quartier_obligatoire(complete_user_factory, scene):
    refused(complete_user_factory(), draft(zone_slug=None), "zone_required")


def test_position_invalide(complete_user_factory, scene):
    refused(complete_user_factory(), draft(location=Point(0, 95, srid=4326)), "location_invalid")


def test_texte_trop_long(complete_user_factory, scene):
    refused(complete_user_factory(), draft(description="x" * 1001), "text_too_long")
    refused(complete_user_factory(), draft(landmark="x" * 301), "text_too_long")


def test_jour_souhaite(complete_user_factory, scene):
    from jeflink.common.dakar import dakar_today

    today = dakar_today(timezone.now())
    ok = create(
        complete_user_factory(),
        draft(
            preferred_when="date",
            preferred_date=today + timedelta(days=2),
            preferred_period="morning",
        ),
    ).request
    assert ok.preferred_date == today + timedelta(days=2) and ok.preferred_period == "morning"
    for bad in (today - timedelta(days=1), today + timedelta(days=31), None):
        refused(
            complete_user_factory(),
            draft(preferred_when="date", preferred_date=bad),
            "slot_invalid",
        )
    refused(complete_user_factory(), draft(preferred_when="demain"), "slot_invalid")


def test_des_que_possible_ignore_le_jour(complete_user_factory, scene):
    today = timezone.localdate()
    request = create(
        complete_user_factory(), draft(preferred_date=today, preferred_period="evening")
    ).request
    assert request.preferred_date is None and request.preferred_period == "any"


def test_limite_de_trois_demandes_non_closes(complete_user_factory, scene):
    client = complete_user_factory()
    created = [create(client, key=f"{i}" * 30).request for i in range(3)]
    refused(client, draft(), "request_limit_reached", key="9" * 30)
    # Une demande annulée libère une place.
    services.cancel_request(request=created[0], actor=client, reason="changed_mind")
    assert create(client, key="8" * 30).created


def test_limite_de_dix_creations_par_jour(complete_user_factory, scene, settings):
    settings.REQUEST_CREATE_DAILY_LIMIT = 2
    settings.REQUEST_MAX_OPEN_PER_CLIENT = 10
    client = complete_user_factory()
    create(client, key="a" * 30)
    create(client, key="b" * 30)
    error = refused(client, draft(), "request_rate_limited", key="c" * 30)
    assert error.status_code == 429 and error.extra["retry_after"] >= 1
    # Le rejeu d'une création déjà faite ne consomme rien.
    assert not create(client, key="a" * 30).created


def test_limite_quotidienne_fermee_si_redis_tombe(complete_user_factory, scene, redis_down):
    error = refused(complete_user_factory(), draft(), "rate_limit_unavailable")
    assert error.status_code == 503
    assert not ServiceRequest.objects.exists()


def test_une_refus_de_disponibilite_ne_consomme_pas_la_limite_quotidienne(
    complete_user_factory, scene, settings
):
    settings.REQUEST_CREATE_DAILY_LIMIT = 1
    client = complete_user_factory()
    refused(client, draft(trade_slug="inconnu"), "trade_not_found", key="a" * 30)
    assert create(client, key="b" * 30).created


def test_meme_cle_meme_corps_rend_la_meme_demande(complete_user_factory, scene):
    client = complete_user_factory()
    first = create(client)
    again = create(client)
    assert first.created and not again.created and first.request.pk == again.request.pk
    assert ServiceRequest.objects.count() == 1


def test_meme_cle_autre_corps_refusee(complete_user_factory, scene):
    client = complete_user_factory()
    create(client)
    refused(client, draft(description="Autre chose"), "idempotency_key_reused")


def test_le_canal_fait_partie_du_corps(complete_user_factory, scene):
    client = complete_user_factory()
    create(client, channel="web")
    with pytest.raises(DomainError) as exc:
        create(client, channel="app")
    assert exc.value.code == "idempotency_key_reused"


def test_une_meme_cle_chez_deux_clients_est_independante(complete_user_factory, scene):
    assert create(complete_user_factory()).created and create(complete_user_factory()).created


@pytest.mark.parametrize("key", ["", "court", "a b" * 10, "é" * 30, "x" * 65])
def test_cle_d_idempotence_obligatoire_et_bien_formee(complete_user_factory, scene, key):
    refused(complete_user_factory(), draft(), "idempotency_key_required", key=key)


def test_canal_inconnu(complete_user_factory, scene):
    with pytest.raises(DomainError) as exc:
        create(complete_user_factory(), channel="sms")
    assert exc.value.code == "channel_invalid"


def test_aucun_pro_eligible_ecrit_un_signal_no_provider(complete_user_factory, scene):
    scene["pro"].trades.clear()
    request = create(complete_user_factory()).request
    assert request.status == "open"
    signal = UnservedDemand.objects.get()
    assert (signal.reason, signal.trade_slug, signal.zone_slug) == (
        "no_provider",
        "plomberie",
        "ouakam",
    )


def test_avec_un_pro_eligible_aucun_signal(complete_user_factory, scene):
    create(complete_user_factory())
    assert not UnservedDemand.objects.exists()


def test_audit_sans_donnee_personnelle(complete_user_factory, scene):
    client = complete_user_factory()
    create(client, draft(description="Rappelez-moi au 771234567"))
    event = AuditEvent.objects.get(action="requests.request.created")
    assert event.metadata == {"status": "open", "channel": "web", "urgent": False}
    assert event.actor_id == client.id


def test_eligibilite_exclusions_et_compte_de_revue(complete_user_factory, scene):
    client = complete_user_factory()
    request = create(client).request
    pro = scene["pro"]
    assert list(eligible_providers(request)) == [pro]
    # Le gérant ne voit pas sa propre demande.
    own = ServiceRequestFactory(client=pro.owner, trade=scene["trade"], zone=scene["zone"])
    assert eligible_providers(own).count() == 0
    # Un pro qui s'est désisté en est exclu.
    request.excluded_providers.add(pro)
    assert eligible_providers(request).count() == 0
    request.excluded_providers.clear()
    # Pro suspendu ou en attente : jamais.
    pro.status = "pending"
    pro.save()
    assert eligible_providers(request).count() == 0
    # Compte de revue : seulement les pros de démo.
    pro.status = "verified"
    pro.save()
    reviewer = complete_user_factory(is_review_account=True)
    review_request = ServiceRequestFactory(
        client=reviewer, trade=scene["trade"], zone=scene["zone"]
    )
    assert eligible_providers(review_request).count() == 0
    pro.is_demo = True
    pro.save()
    assert eligible_providers(review_request).count() == 1


def test_needs_zone_n_a_pas_de_pro_eligible(complete_user_factory, scene):
    request = create(complete_user_factory(), draft(zone_slug=None, zone_text="inconnu")).request
    assert eligible_providers(request).count() == 0


def test_demande_reserve_comme_slug_de_metier():
    with pytest.raises(ValidationError) as exc:
        Trade(slug="demande", name_fr="Demande").clean()
    assert exc.value.error_dict["slug"][0].code == "slug_reserved"
