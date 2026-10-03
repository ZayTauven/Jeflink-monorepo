from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from jeflink.catalog.tests.factories import TradeFactory
from jeflink.common.dakar import dakar_today
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import ProviderFactory, VerifiedProviderFactory
from jeflink.requests import quotes, services, tasks
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.quotes import QuoteInput, QuoteLineInput
from jeflink.requests.selectors import (
    places_left,
    quote_for_client,
    quote_for_provider,
    quotes_for_client_request,
    request_for_provider,
    requests_for_provider,
)
from jeflink.trust.models import AuditEvent
from jeflink.zones.tests.factories import ZoneFactory

from .factories import ServiceRequestFactory

pytestmark = pytest.mark.django_db
Status = ServiceRequest.Status
QStatus = Quote.Status


@pytest.fixture
def scene():
    trade = TradeFactory()
    zone = ZoneFactory(trades=[trade])
    request = ServiceRequestFactory(trade=trade, zone=zone)
    return {"trade": trade, "zone": zone, "request": request}


def new_pro(scene, **kwargs):
    return VerifiedProviderFactory(trades=[scene["trade"]], zones=[scene["zone"]], **kwargs)


def tomorrow():
    return dakar_today(timezone.now()) + timedelta(days=1)


def content(**overrides) -> QuoteInput:
    base = {
        "kind": "fixed",
        "total_xof": 15_000,
        "lines": (
            QuoteLineInput("labor", 10_000, "Remplacement du joint"),
            QuoteLineInput("parts", 5_000),
        ),
        "slot_day": tomorrow(),
        "slot_period": "morning",
    }
    return QuoteInput(**{**base, **overrides})


_counter = iter(range(10_000))


def send(pro, request, c=None, *, key=None):
    return quotes.submit_quote(
        provider=pro,
        request=request,
        content=c or content(),
        idempotency_key=key or f"quote-key-{next(_counter):020d}",
    )


def refused(pro, request, code, c=None, *, key=None, status=None):
    with pytest.raises(DomainError) as exc:
        send(pro, request, c, key=key)
    assert exc.value.code == code
    if status:
        assert exc.value.status_code == status
    return exc.value


def test_envoi_d_un_devis(scene):
    pro, request = new_pro(scene), scene["request"]
    result = send(pro, request)
    quote = result.quote
    assert result.created and quote.status == QStatus.SUBMITTED
    assert [(line.kind, line.amount_xof) for line in quote.lines.all()] == [
        ("labor", 10_000),
        ("parts", 5_000),
    ]
    assert quote.total_xof == 15_000 and quote.slot_end > quote.slot_start
    request.refresh_from_db()
    assert request.status == Status.QUOTED and request.first_quoted_at is not None
    event = AuditEvent.objects.get(action="requests.quote.submitted")
    assert event.metadata == {"kind": "fixed"}


def test_validite_48h_ou_12h_si_urgente_bornee_par_la_demande(scene):
    pro = new_pro(scene)
    quote = send(pro, scene["request"]).quote
    assert timedelta(hours=47) < quote.valid_until - timezone.now() <= timedelta(hours=48)
    urgent = ServiceRequestFactory(trade=scene["trade"], zone=scene["zone"], urgent=True)
    quote = send(pro, urgent).quote
    assert timedelta(hours=11) < quote.valid_until - timezone.now() <= timedelta(hours=12)
    short = ServiceRequestFactory(
        trade=scene["trade"], zone=scene["zone"], expires_at=timezone.now() + timedelta(hours=5)
    )
    assert send(pro, short).quote.valid_until == short.expires_at


def test_idempotence(scene):
    pro, request = new_pro(scene), scene["request"]
    first = send(pro, request, key="same-key-" + "0" * 20)
    again = send(pro, request, key="same-key-" + "0" * 20)
    assert not again.created and again.quote.pk == first.quote.pk
    assert Quote.objects.count() == 1
    refused(
        pro, request, "idempotency_key_reused", content(slot_period="afternoon"),
        key="same-key-" + "0" * 20,
    )  # fmt: skip
    refused(pro, request, "idempotency_key_required", key="trop-court")


@pytest.mark.parametrize(
    ("c", "code"),
    [
        (content(total_xof=14_999), "quote_total_invalid"),
        (content(lines=()), "quote_total_invalid"),
        (content(lines=(QuoteLineInput("labor", 0),), total_xof=0), "quote_total_invalid"),
        (
            content(lines=(QuoteLineInput("labor", 5_000_001),), total_xof=5_000_001),
            "quote_total_invalid",
        ),
        (
            content(lines=tuple(QuoteLineInput("labor", 100) for _ in range(9)), total_xof=900),
            "quote_total_invalid",
        ),
        (content(lines=(QuoteLineInput("autre", 100),), total_xof=100), "quote_total_invalid"),
        (content(kind="gratuit"), "quote_total_invalid"),
        (
            content(lines=(QuoteLineInput("parts", 5_000),), total_xof=5_000),
            "quote_details_required",
        ),
        (content(message="x" * 501), "text_too_long"),
        (content(slot_period="nuit"), "slot_invalid"),
    ],
)
def test_devis_invalides(scene, c, code):
    refused(new_pro(scene), scene["request"], code, c, status=422)
    assert not Quote.objects.exists()


def test_prix_ferme_sans_main_d_oeuvre_accepte_avec_un_vrai_message(scene):
    pro = new_pro(scene)
    c = content(
        lines=(QuoteLineInput("parts", 5_000),),
        total_xof=5_000,
        message="Fourniture et pose du robinet neuf",
    )
    assert send(pro, scene["request"], c).created


def test_visite_seulement_plafonnee(scene):
    pro = new_pro(scene)
    ok = content(
        kind="visit", total_xof=15_000, lines=(QuoteLineInput("travel", 15_000),),
        visit_deductible=True,
    )  # fmt: skip
    quote = send(pro, scene["request"], ok).quote
    assert quote.visit_deductible and quote.kind == "visit"
    other = new_pro(scene)
    too_much = content(kind="visit", total_xof=15_001, lines=(QuoteLineInput("travel", 15_001),))
    refused(other, scene["request"], "quote_total_invalid", too_much)


def test_deductible_ignore_hors_visite(scene):
    quote = send(new_pro(scene), scene["request"], content(visit_deductible=True)).quote
    assert quote.visit_deductible is False


def test_creneau_dans_le_passe_ou_trop_loin(scene, settings):
    pro = new_pro(scene)
    today = dakar_today(timezone.now())
    refused(pro, scene["request"], "slot_invalid", content(slot_day=today - timedelta(days=1)))
    refused(pro, scene["request"], "slot_invalid", content(slot_day=today + timedelta(days=31)))
    settings.SLOT_PERIODS = {"morning": (0, 1), "afternoon": (1, 2), "evening": (2, 3)}
    refused(pro, scene["request"], "slot_invalid", content(slot_day=today))  # minuit déjà passé


def test_trois_places_puis_quotes_full_et_retrait_libere(scene):
    request = scene["request"]
    pros = [new_pro(scene) for _ in range(4)]
    sent = [send(pro, request).quote for pro in pros[:3]]
    assert places_left(request) == 0
    error = refused(pros[3], request, "quotes_full", status=409)
    assert error.status_code == 409
    quotes.withdraw_quote(quote=sent[0], provider=pros[0])
    assert places_left(request) == 1
    assert send(pros[3], request).created


def test_la_demande_sort_de_la_liste_quand_pleine_et_y_revient(scene):
    request = scene["request"]
    pros = [new_pro(scene) for _ in range(4)]
    sent = [send(pro, request).quote for pro in pros[:3]]
    assert not requests_for_provider(provider=pros[3]).exists()
    quotes.withdraw_quote(quote=sent[1], provider=pros[1])
    assert list(requests_for_provider(provider=pros[3])) == [request]


def test_un_seul_devis_actif_par_pro_et_par_demande(scene):
    pro, request = new_pro(scene), scene["request"]
    first = send(pro, request).quote
    refused(pro, request, "quote_already_sent", status=409)
    # Pour modifier : retirer puis renvoyer.
    quotes.withdraw_quote(quote=first, provider=pro)
    assert send(pro, request).created


def test_plafond_de_devis_en_attente_par_pro(scene, settings):
    settings.PRO_MAX_SUBMITTED_QUOTES = 2
    pro = new_pro(scene)
    for _ in range(2):
        send(pro, ServiceRequestFactory(trade=scene["trade"], zone=scene["zone"]))
    refused(
        pro,
        ServiceRequestFactory(trade=scene["trade"], zone=scene["zone"]),
        "pro_quote_limit",
        status=409,
    )


def test_demande_de_son_propre_gerant_refusee(scene):
    pro = new_pro(scene)
    own = ServiceRequestFactory(client=pro.owner, trade=scene["trade"], zone=scene["zone"])
    refused(pro, own, "own_request", status=403)


@pytest.mark.parametrize(
    "closed", [Status.CANCELLED, Status.EXPIRED, Status.BOOKED, Status.NEEDS_ZONE]
)
def test_demande_close_refusee(scene, closed):
    request = ServiceRequestFactory(trade=scene["trade"], zone=scene["zone"], status=closed)
    refused(new_pro(scene), request, "request_closed", status=409)


def test_demande_echue_meme_sans_la_tache(scene):
    request = ServiceRequestFactory(
        trade=scene["trade"], zone=scene["zone"], expires_at=timezone.now() - timedelta(minutes=1)
    )
    refused(new_pro(scene), request, "request_closed", status=409)


def test_demande_invisible_du_pro_est_un_404(scene):
    request = scene["request"]
    other_trade = ProviderFactory(status="verified", trades=[TradeFactory()], zones=[scene["zone"]])
    other_zone = ProviderFactory(status="verified", trades=[scene["trade"]], zones=[ZoneFactory()])
    for pro in (other_trade, other_zone):
        refused(pro, request, "not_found", status=404)
    excluded = new_pro(scene)
    request.excluded_providers.add(excluded)
    refused(excluded, request, "not_found", status=404)


@pytest.mark.parametrize("status", ["pending", "suspended"])
def test_pro_non_verifie_ne_devise_pas(scene, status):
    pro = ProviderFactory(status=status, trades=[scene["trade"]], zones=[scene["zone"]])
    refused(pro, scene["request"], "provider_not_verified", status=403)


def test_numero_dans_le_message_compte_sans_garder_le_texte_dans_l_audit(scene):
    pro = new_pro(scene)
    c = content(message="Appelez-moi au 77 123 45 67 pour fixer l'heure")
    quote = send(pro, scene["request"], c).quote
    pro.refresh_from_db()
    assert pro.masked_numbers_count == 1
    assert "77 123 45 67" in quote.message  # le texte stocké reste intact
    assert "123" not in str([e.metadata for e in AuditEvent.objects.all()])


def test_retrait(scene):
    request = scene["request"]
    pro_a, pro_b = new_pro(scene), new_pro(scene)
    a, b = send(pro_a, request).quote, send(pro_b, request).quote
    quotes.withdraw_quote(quote=a, provider=pro_a)
    request.refresh_from_db()
    assert request.status == Status.QUOTED  # il en reste un
    quotes.withdraw_quote(quote=b, provider=pro_b)
    request.refresh_from_db()
    assert request.status == Status.OPEN
    a.refresh_from_db()
    assert a.status == QStatus.WITHDRAWN


def test_retrait_refuse(scene):
    request = scene["request"]
    pro, other = new_pro(scene), new_pro(scene)
    quote = send(pro, request).quote
    with pytest.raises(DomainError) as exc:
        quotes.withdraw_quote(quote=quote, provider=other)
    assert exc.value.status_code == 404
    for status in (QStatus.HELD, QStatus.ACCEPTED, QStatus.DECLINED, QStatus.EXPIRED):
        Quote.objects.filter(pk=quote.pk).update(status=status)
        with pytest.raises(DomainError) as exc:
            quotes.withdraw_quote(quote=quote, provider=pro)
        assert (exc.value.code, exc.value.status_code) == ("quote_not_available", 409)


def test_expiration_des_devis_remet_la_demande_a_open(scene):
    request = scene["request"]
    pro = new_pro(scene)
    quote = send(pro, request).quote
    Quote.objects.filter(pk=quote.pk).update(valid_until=timezone.now() - timedelta(minutes=1))
    assert quotes.expire_quotes() == 1
    quote.refresh_from_db()
    request.refresh_from_db()
    assert quote.status == QStatus.EXPIRED and request.status == Status.OPEN
    assert quotes.expire_quotes() == 0
    # Le pro peut renvoyer un devis : l'ancien n'est plus actif.
    assert send(pro, request).created


def test_la_tache_expire_les_demandes_et_les_devis(scene):
    request = scene["request"]
    quote = send(new_pro(scene), request).quote
    Quote.objects.filter(pk=quote.pk).update(valid_until=timezone.now() - timedelta(minutes=1))
    other = ServiceRequestFactory(expires_at=timezone.now() - timedelta(minutes=1))
    assert tasks.expire_due() == {"requests": 1, "quotes": 1}
    other.refresh_from_db()
    assert other.status == Status.EXPIRED


def test_un_devis_echu_n_est_plus_montre_au_client_meme_sans_la_tache(scene):
    request = scene["request"]
    quote = send(new_pro(scene), request).quote
    assert list(quotes_for_client_request(request)) == [quote]
    Quote.objects.filter(pk=quote.pk).update(valid_until=timezone.now() - timedelta(minutes=1))
    assert list(quotes_for_client_request(request)) == []


def test_annulation_de_la_demande_refuse_les_devis(scene):
    request = scene["request"]
    quote = send(new_pro(scene), request).quote
    services.cancel_request(request=request, actor=request.client, reason="price")
    quote.refresh_from_db()
    assert quote.status == QStatus.DECLINED


def test_expiration_de_la_demande_expire_les_devis(scene):
    request = scene["request"]
    quote = send(new_pro(scene), request).quote
    ServiceRequest.objects.filter(pk=request.pk).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    services.expire_due()
    quote.refresh_from_db()
    assert quote.status == QStatus.EXPIRED


def test_suspension_du_pro_retire_ses_devis(scene):
    from jeflink.providers.services import set_status

    request = scene["request"]
    pro = new_pro(scene)
    quote = send(pro, request).quote
    set_status(provider=pro, to=Provider.Status.SUSPENDED, actor=request.client)
    quote.refresh_from_db()
    request.refresh_from_db()
    assert quote.status == QStatus.WITHDRAWN and request.status == Status.OPEN


def test_anonymiseur_du_pro_efface_les_messages(scene):
    from jeflink.accounts.deletion import _anonymize

    pro = new_pro(scene)
    quote = send(
        pro,
        scene["request"],
        content(message="Message du pro", lines=(QuoteLineInput("labor", 15_000, "Joint"),)),
    ).quote
    _anonymize(pro.owner, reason="user_request")
    quote.refresh_from_db()
    assert quote.message == "" and quote.lines.get().label == ""
    assert quote.status == QStatus.WITHDRAWN


def test_anonymiseur_du_client_refuse_les_devis_en_cours(scene):
    from jeflink.accounts.deletion import _anonymize

    quote = send(new_pro(scene), scene["request"]).quote
    _anonymize(scene["request"].client, reason="user_request")
    quote.refresh_from_db()
    assert quote.status == QStatus.DECLINED


# --- Sélecteurs -----------------------------------------------------------------------------------


def test_demandes_pour_moi_ordre_urgence_puis_anciennete(scene):
    pro = new_pro(scene)
    first = scene["request"]
    second = ServiceRequestFactory(trade=scene["trade"], zone=scene["zone"])
    urgent = ServiceRequestFactory(trade=scene["trade"], zone=scene["zone"], urgent=True)
    assert list(requests_for_provider(provider=pro)) == [urgent, first, second]


def test_demandes_pour_moi_filtres(scene):
    pro = new_pro(scene)
    visible = scene["request"]
    ServiceRequestFactory(trade=TradeFactory(), zone=scene["zone"])  # autre métier
    ServiceRequestFactory(trade=scene["trade"], zone=ZoneFactory())  # autre zone
    ServiceRequestFactory(client=pro.owner, trade=scene["trade"], zone=scene["zone"])  # la sienne
    ServiceRequestFactory(
        trade=scene["trade"], zone=scene["zone"], expires_at=timezone.now() - timedelta(minutes=1)
    )  # échue, tâche en retard
    ServiceRequestFactory(trade=scene["trade"], zone=scene["zone"], status=Status.CANCELLED)
    assert list(requests_for_provider(provider=pro)) == [visible]
    # Elle disparaît une fois devisée par ce pro.
    send(pro, visible)
    assert not requests_for_provider(provider=pro).exists()
    # Pro non vérifié : rien.
    pending = ProviderFactory(trades=[scene["trade"]], zones=[scene["zone"]])
    assert not requests_for_provider(provider=pending).exists()


def test_compte_de_revue_visible_des_seuls_pros_de_demo(scene):
    from jeflink.accounts.tests.factories import CompleteUserFactory

    reviewer = CompleteUserFactory(is_review_account=True)
    request = ServiceRequestFactory(client=reviewer, trade=scene["trade"], zone=scene["zone"])
    assert not requests_for_provider(provider=new_pro(scene)).filter(pk=request.pk).exists()
    assert (
        requests_for_provider(provider=new_pro(scene, is_demo=True)).filter(pk=request.pk).exists()
    )


def test_request_for_provider_garde_la_demande_pleine_visible_pour_le_409(scene):
    request = scene["request"]
    pros = [new_pro(scene) for _ in range(4)]
    for pro in pros[:3]:
        send(pro, request)
    assert request_for_provider(provider=pros[3], public_id=request.public_id).pk == request.pk
    stranger = ProviderFactory(status="verified", trades=[TradeFactory()], zones=[scene["zone"]])
    with pytest.raises(DomainError) as exc:
        request_for_provider(provider=stranger, public_id=request.public_id)
    assert exc.value.status_code == 404


def test_devis_du_client_tries_par_creneau_jamais_par_prix(scene):
    request = scene["request"]
    late = send(
        new_pro(scene),
        request,
        content(slot_period="evening", total_xof=5_000, lines=(QuoteLineInput("labor", 5_000),)),
    ).quote
    early = send(
        new_pro(scene),
        request,
        content(slot_period="morning", total_xof=90_000, lines=(QuoteLineInput("labor", 90_000),)),
    ).quote
    assert list(quotes_for_client_request(request)) == [early, late]


def test_devis_d_un_autre_est_un_404(scene):
    from jeflink.accounts.tests.factories import CompleteUserFactory

    pro = new_pro(scene)
    quote = send(pro, scene["request"]).quote
    assert quote_for_client(user=scene["request"].client, public_id=quote.public_id) == quote
    assert quote_for_provider(provider=pro, public_id=quote.public_id) == quote
    with pytest.raises(DomainError) as exc:
        quote_for_client(user=CompleteUserFactory(), public_id=quote.public_id)
    assert exc.value.status_code == 404
    with pytest.raises(DomainError) as exc:
        quote_for_provider(provider=new_pro(scene), public_id=quote.public_id)
    assert exc.value.status_code == 404


# --- Concurrence (transaction réelle) --------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_cinq_pros_en_meme_temps_trois_places():
    from concurrent.futures import ThreadPoolExecutor

    trade = TradeFactory()
    zone = ZoneFactory(trades=[trade])
    request = ServiceRequestFactory(trade=trade, zone=zone)
    pros = [VerifiedProviderFactory(trades=[trade], zones=[zone]) for _ in range(5)]

    def attempt(pro):
        try:
            return send(pro, request).created
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(attempt, pros))
    assert results.count(True) == 3 and results.count("quotes_full") == 2
    assert Quote.objects.filter(request=request, status__in=Quote.ACTIVE).count() == 3
