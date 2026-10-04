"""API du pro : demandes pour moi, devis, réservations (spec 003) : autorisé, refusé, invalide.

Le pro ne reçoit jamais le nom, le numéro, le repère ou la position du client avant ``scheduled``
(ni après une annulation) : testé statut par statut.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings.machine import DISCLOSED_STATUSES
from jeflink.bookings.models import Booking
from jeflink.bookings.tests.factories import quote_input
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.common.dakar import dakar_today
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import ProviderFactory, VerifiedProviderFactory
from jeflink.requests.models import Quote
from jeflink.requests.tests.factories import ServiceRequestFactory
from jeflink.requests.tests.test_requests_api import bearer
from jeflink.zones.tests.factories import ZoneFactory

pytestmark = pytest.mark.django_db
KEY = "pro-key-" + "0" * 24
GPS = {"lat": 14.7167, "lon": -17.4677}


@pytest.fixture
def world():
    trade = TradeFactory()
    zone = ZoneFactory(trades=[trade])
    pro = VerifiedProviderFactory(trades=[trade], zones=[zone], business_name="Plomberie Ibou")
    client = CompleteUserFactory(display_name="Awa Ndiaye", phone="+221771112233")
    from django.contrib.gis.geos import Point

    request = ServiceRequestFactory(
        client=client,
        trade=trade,
        zone=zone,
        landmark="derrière la mosquée, portail bleu",
        description="Fuite. Appelez-moi au 77 123 45 67",
        location=Point(GPS["lon"], GPS["lat"], srid=4326),
    )
    return {"trade": trade, "zone": zone, "pro": pro, "client": client, "request": request}


def quote_body(**overrides):
    base = {
        "kind": "fixed",
        "total_xof": 15_000,
        "lines": [{"kind": "labor", "amount_xof": 15_000, "label": "Remplacement du joint"}],
        "slot_day": (dakar_today(timezone.now()) + timedelta(days=1)).isoformat(),
        "slot_period": "morning",
        "message": "",
    }
    return {**base, **overrides}


def pro_api(api_client, pro):
    return bearer(api_client, pro.owner, app="pro")


SECRETS = ("Awa", "Ndiaye", "+221771112233", "771112233", "mosquée", "portail bleu", "14.7167",
           "-17.4677", "77 123 45 67")  # fmt: skip


def assert_no_client_data(response):
    text = response.content.decode()
    for secret in SECRETS:
        assert secret not in text, secret


# --- GET /api/pro/me/ --------------------------------------------------------------------------


def test_ma_fiche(api_client, world):
    response = pro_api(api_client, world["pro"]).get(reverse("pro-me"))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "verified" and data["business_name"] == "Plomberie Ibou"
    assert [t["slug"] for t in data["trades"]] == [world["trade"].slug]
    assert [z["slug"] for z in data["zones"]] == [world["zone"].slug]
    assert "owner" not in data and "masked_numbers_count" not in data


def test_ma_fiche_en_attente_ou_suspendue_se_lit(api_client):
    for status in ("pending", "suspended"):
        pro = ProviderFactory(status=status)
        assert pro_api(api_client, pro).get(reverse("pro-me")).json()["status"] == status


def test_ma_fiche_refusee_a_un_client_sans_role_ou_sans_fiche(api_client):
    response = bearer(api_client, CompleteUserFactory()).get(reverse("pro-me"))
    assert (response.status_code, response.json()["code"]) == (403, "role_required")
    from jeflink.accounts.models import Role, RoleGrant

    owner = CompleteUserFactory()
    RoleGrant.objects.create(user=owner, role=Role.OWNER, reason_code="test")
    assert bearer(api_client, owner).get(reverse("pro-me")).status_code == 404
    api_client.credentials()
    assert api_client.get(reverse("pro-me")).status_code == 401


# --- GET /api/pro/requests/ --------------------------------------------------------------------


def test_demandes_pour_moi_sans_aucune_donnee_du_client(api_client, world):
    api = pro_api(api_client, world["pro"])
    response = api.get(reverse("pro-requests"))
    assert response.status_code == 200
    (item,) = response.json()["results"]
    assert item["public_id"] == str(world["request"].public_id)
    assert item["places_left"] == 3 and item["places_total"] == 3
    assert item["trade"]["slug"] == world["trade"].slug and item["zone"]["slug"]
    assert "••••" in item["description"] and "77 123 45 67" not in item["description"]
    assert not {"client", "landmark", "location", "phone", "has_location"} & set(item)
    assert_no_client_data(response)
    detail = api.get(reverse("pro-request-detail", args=[world["request"].public_id]))
    assert detail.status_code == 200
    assert_no_client_data(detail)


def test_ordre_urgence_puis_anciennete_et_curseur(api_client, world):
    older = world["request"]
    urgent = ServiceRequestFactory(trade=world["trade"], zone=world["zone"], urgent=True)
    newer = ServiceRequestFactory(trade=world["trade"], zone=world["zone"])
    for _ in range(20):
        ServiceRequestFactory(trade=world["trade"], zone=world["zone"])
    api = pro_api(api_client, world["pro"])
    page = api.get(reverse("pro-requests")).json()
    ids = [r["public_id"] for r in page["results"]]
    assert ids[0] == str(urgent.public_id) and ids[1] == str(older.public_id)
    assert ids[2] == str(newer.public_id)
    second = api.get(page["next"]).json()
    assert len(page["results"]) + len(second["results"]) == 23
    assert not set(ids) & {r["public_id"] for r in second["results"]}


def test_places_restantes_sans_les_montants_des_autres(api_client, world):
    other = VerifiedProviderFactory(trades=[world["trade"]], zones=[world["zone"]])
    api_other = pro_api(api_client, other)
    from jeflink.requests import quotes
    from jeflink.requests.quotes import QuoteInput

    content: QuoteInput = quote_input(amount=99_000)
    quotes.submit_quote(
        provider=other, request=world["request"], content=content, idempotency_key="o" * 30
    )
    response = pro_api(api_client, world["pro"]).get(
        reverse("pro-request-detail", args=[world["request"].public_id])
    )
    assert response.json()["places_left"] == 2
    assert "99000" not in response.content.decode() and "total_xof" not in response.content.decode()
    # Celui qui a déjà deviné ne voit plus la demande dans sa liste.
    assert api_other.get(reverse("pro-requests")).json()["results"] == []


def test_demande_d_un_autre_metier_ou_d_une_autre_zone_404(api_client, world):
    elsewhere = ServiceRequestFactory(trade=TradeFactory(), zone=world["zone"])
    api = pro_api(api_client, world["pro"])
    response = api.get(reverse("pro-request-detail", args=[elsewhere.public_id]))
    assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert [r["public_id"] for r in api.get(reverse("pro-requests")).json()["results"]] == [
        str(world["request"].public_id)
    ]


@pytest.mark.parametrize("status", ["pending", "suspended"])
def test_pro_non_verifie_refuse_partout(api_client, world, status):
    pro = ProviderFactory(status=status, trades=[world["trade"]], zones=[world["zone"]])
    api = pro_api(api_client, pro)
    rid = world["request"].public_id
    for response in (
        api.get(reverse("pro-requests")),
        api.get(reverse("pro-request-detail", args=[rid])),
        api.post(reverse("pro-request-quote", args=[rid]), quote_body(), format="json",
                 HTTP_IDEMPOTENCY_KEY=KEY),
        api.get(reverse("pro-quotes")),
    ):  # fmt: skip
        assert response.status_code == 403
        assert response.json()["code"] == "provider_not_verified"


def test_un_client_simple_est_refuse_sur_les_routes_pro(api_client, world):
    api = bearer(api_client, CompleteUserFactory())
    rid = world["request"].public_id
    for response in (
        api.get(reverse("pro-requests")),
        api.get(reverse("pro-request-detail", args=[rid])),
        api.post(reverse("pro-request-quote", args=[rid]), quote_body(), format="json"),
        api.get(reverse("pro-quotes")),
        api.get(reverse("pro-bookings")),
    ):
        assert (response.status_code, response.json()["code"]) == (403, "role_required")


def test_la_demande_de_son_propre_gerant_n_est_pas_visible(api_client, world):
    own = ServiceRequestFactory(client=world["pro"].owner, trade=world["trade"], zone=world["zone"])
    api = pro_api(api_client, world["pro"])
    assert api.get(reverse("pro-request-detail", args=[own.public_id])).status_code == 404


# --- POST /api/pro/requests/{id}/quotes/ -------------------------------------------------------


def send_quote(api, request, data=None, key=KEY):
    return api.post(
        reverse("pro-request-quote", args=[request.public_id]),
        data if data is not None else quote_body(),
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


def test_envoi_d_un_devis_201_puis_rejeu_200(api_client, world):
    api = pro_api(api_client, world["pro"])
    first = send_quote(api, world["request"])
    again = send_quote(api, world["request"])
    assert (first.status_code, again.status_code) == (201, 200)
    data = first.json()
    assert data["status"] == "submitted" and data["total_xof"] == 15_000
    assert data["request"] == str(world["request"].public_id)
    assert data["lines"] == [
        {"kind": "labor", "label": "Remplacement du joint", "amount_xof": 15_000}
    ]
    assert data["public_id"] == again.json()["public_id"] and Quote.objects.count() == 1
    assert_no_client_data(first)
    mine = api.get(reverse("pro-quotes")).json()["results"]
    assert [q["public_id"] for q in mine] == [data["public_id"]]


def test_envoi_autre_corps_meme_cle_409_et_cle_manquante_400(api_client, world):
    api = pro_api(api_client, world["pro"])
    send_quote(api, world["request"])
    response = send_quote(api, world["request"], quote_body(message="x" * 30))
    assert (response.status_code, response.json()["code"]) == (409, "idempotency_key_reused")
    missing = api.post(
        reverse("pro-request-quote", args=[world["request"].public_id]), quote_body(), format="json"
    )
    assert (missing.status_code, missing.json()["code"]) == (400, "idempotency_key_required")


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"total_xof": 14_000}, "quote_total_invalid"),
        ({"kind": "visit", "total_xof": 20_000,
          "lines": [{"kind": "travel", "amount_xof": 20_000}]},
         "quote_total_invalid"),
        ({"lines": [{"kind": "parts", "amount_xof": 15_000}]}, "quote_details_required"),
        ({"slot_period": "nuit"}, "slot_invalid"),
        ({"slot_day": "2001-01-01"}, "slot_invalid"),
    ],
)  # fmt: skip
def test_devis_refuse_422(api_client, world, overrides, code):
    response = send_quote(
        pro_api(api_client, world["pro"]), world["request"], quote_body(**overrides)
    )
    assert (response.status_code, response.json()["code"]) == (422, code)


def test_devis_mal_forme_400(api_client, world):
    api = pro_api(api_client, world["pro"])
    for data in ({}, quote_body(slot_day="demain"), quote_body(total_xof="beaucoup")):
        response = send_quote(api, world["request"], data)
        assert (response.status_code, response.json()["code"]) == (400, "invalid")


def test_quatrieme_devis_409_quotes_full_et_deja_envoye(api_client, world):
    api = pro_api(api_client, world["pro"])
    assert send_quote(api, world["request"]).status_code == 201
    again = send_quote(api, world["request"], key="n" * 30)
    assert (again.status_code, again.json()["code"]) == (409, "quote_already_sent")
    for index in range(2):
        other = VerifiedProviderFactory(trades=[world["trade"]], zones=[world["zone"]])
        assert (
            send_quote(
                pro_api(api_client, other), world["request"], key=f"{index}" * 30
            ).status_code
            == 201
        )
    fourth = VerifiedProviderFactory(trades=[world["trade"]], zones=[world["zone"]])
    response = send_quote(pro_api(api_client, fourth), world["request"], key="f" * 30)
    assert (response.status_code, response.json()["code"]) == (409, "quotes_full")
    # Un retrait libère une place, et la demande revient dans la liste.
    mine = api.get(reverse("pro-quotes")).json()["results"][0]
    withdrawn = api.post(reverse("pro-quote-withdraw", args=[mine["public_id"]]))
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "withdrawn"
    listed = pro_api(api_client, fourth).get(reverse("pro-requests")).json()["results"]
    assert [r["public_id"] for r in listed] == [str(world["request"].public_id)]
    assert (
        send_quote(pro_api(api_client, fourth), world["request"], key="g" * 30).status_code == 201
    )


def test_demande_close_409_et_sans_session_401(api_client, world):
    world["request"].status = "cancelled"
    world["request"].save()
    response = send_quote(pro_api(api_client, world["pro"]), world["request"])
    assert response.status_code == 404  # une demande close sort de la vue du pro
    assert (
        api_client.post(
            reverse("pro-request-quote", args=[world["request"].public_id]),
            quote_body(),
            format="json",
        ).status_code
        == 401
    )


def test_plafond_de_devis_en_attente_409(api_client, world, settings):
    settings.PRO_MAX_SUBMITTED_QUOTES = 1
    api = pro_api(api_client, world["pro"])
    second = ServiceRequestFactory(trade=world["trade"], zone=world["zone"])
    assert send_quote(api, world["request"]).status_code == 201
    response = send_quote(api, second, key="s" * 30)
    assert (response.status_code, response.json()["code"]) == (409, "pro_quote_limit")


# --- Retrait d'un devis ------------------------------------------------------------------------


def test_retrait_d_un_devis_d_un_autre_pro_404(api_client, world):
    api = pro_api(api_client, world["pro"])
    quote = send_quote(api, world["request"]).json()
    other = VerifiedProviderFactory(trades=[world["trade"]], zones=[world["zone"]])
    response = pro_api(api_client, other).post(
        reverse("pro-quote-withdraw", args=[quote["public_id"]])
    )
    assert (response.status_code, response.json()["code"]) == (404, "not_found")
    again = api.post(reverse("pro-quote-withdraw", args=[quote["public_id"]]))
    second = api.post(reverse("pro-quote-withdraw", args=[quote["public_id"]]))
    assert (again.status_code, second.status_code) == (200, 409)
    assert second.json()["code"] == "quote_not_available"


# --- Réservations côté pro ---------------------------------------------------------------------


@pytest.fixture
def booked(world):
    """Une réservation ``accepted`` sur la demande du monde, avec les données du client."""
    from jeflink.bookings import services
    from jeflink.requests import quotes

    created = quotes.submit_quote(
        provider=world["pro"],
        request=world["request"],
        content=quote_input(),
        idempotency_key="b" * 30,
    )
    booking = services.create_from_quote(quote=created.quote, actor=world["client"]).booking
    return booking


def test_reservation_a_confirmer_sans_donnee_du_client(api_client, world, booked):
    api = pro_api(api_client, world["pro"])
    listing = api.get(reverse("pro-bookings"))
    detail = api.get(reverse("pro-booking-detail", args=[booked.public_id]))
    for response in (listing, detail):
        assert response.status_code == 200
        assert_no_client_data(response)
    data = detail.json()
    assert data["status"] == "accepted"
    assert data["client"] is None and data["landmark"] is None and data["location"] is None
    assert "••••" in data["description"]
    assert data["confirm_deadline"] and data["amount_xof"] == 15_000


@pytest.mark.parametrize("status", Booking.Status.values)
def test_donnees_du_client_divulguees_seulement_aux_statuts_prevus(
    api_client, world, booked, status
):
    Booking.objects.filter(pk=booked.pk).update(
        status=status, cancelled_by="system" if status == "cancelled" else ""
    )
    response = pro_api(api_client, world["pro"]).get(
        reverse("pro-booking-detail", args=[booked.public_id])
    )
    data = response.json()
    if status in DISCLOSED_STATUSES:
        assert data["client"] == {"display_name": "Awa Ndiaye", "phone": "+221771112233"}
        assert data["landmark"] == "derrière la mosquée, portail bleu"
        assert data["location"] == {
            "lat": pytest.approx(GPS["lat"]),
            "lon": pytest.approx(GPS["lon"]),
        }
        assert "77 123 45 67" in data["description"]
    else:  # accepted, annulée, clôturée : jamais
        assert data["client"] is None and data["landmark"] is None and data["location"] is None
        assert_no_client_data(response)


def test_le_pro_confirme_et_recoit_le_contact(api_client, world, booked):
    api = pro_api(api_client, world["pro"])
    response = api.post(reverse("pro-booking-confirm", args=[booked.public_id]))
    assert response.status_code == 200 and response.json()["status"] == "scheduled"
    assert response.json()["client"]["phone"] == "+221771112233"
    assert response.json()["landmark"] == "derrière la mosquée, portail bleu"
    again = api.post(reverse("pro-booking-confirm", args=[booked.public_id]))
    assert (again.status_code, again.json()["code"]) == (409, "transition_not_allowed")


def test_confirmation_par_un_autre_pro_404(api_client, world, booked):
    other = VerifiedProviderFactory(trades=[world["trade"]], zones=[world["zone"]])
    api = pro_api(api_client, other)
    for response in (
        api.get(reverse("pro-booking-detail", args=[booked.public_id])),
        api.post(reverse("pro-booking-confirm", args=[booked.public_id])),
        api.post(reverse("pro-booking-cancel", args=[booked.public_id]), {"reason": "unavailable"},
                 format="json"),
    ):  # fmt: skip
        assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert api.get(reverse("pro-bookings")).json()["results"] == []


def test_le_pro_se_desiste(api_client, world, booked):
    api = pro_api(api_client, world["pro"])
    response = api.post(
        reverse("pro-booking-cancel", args=[booked.public_id]), {"reason": "too_far"}, format="json"
    )
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["cancelled_by"]) == ("cancelled", "pro")
    assert_no_client_data(response)
    for data, code in (
        ({"reason": "price"}, "reason_invalid"),
        ({"reason": "other"}, "note_invalid"),
    ):
        again = api.post(
            reverse("pro-booking-cancel", args=[booked.public_id]), data, format="json"
        )
        assert again.json()["code"] in {code, "transition_not_allowed"}


def test_pro_suspendu_lit_mais_n_ecrit_plus(api_client, world, booked):
    Provider.objects.filter(pk=world["pro"].pk).update(status="suspended")
    api = pro_api(api_client, world["pro"])
    assert api.get(reverse("pro-bookings")).status_code == 200
    assert api.get(reverse("pro-booking-detail", args=[booked.public_id])).status_code == 200
    for response in (
        api.post(reverse("pro-booking-confirm", args=[booked.public_id])),
        api.post(reverse("pro-booking-cancel", args=[booked.public_id]), {"reason": "unavailable"},
                 format="json"),
    ):  # fmt: skip
        assert (response.status_code, response.json()["code"]) == (403, "provider_not_verified")
    booked.refresh_from_db()
    assert booked.status == "accepted"


def test_reservation_echue_n_est_plus_visible_du_pro(api_client, world, booked):
    Booking.objects.filter(pk=booked.pk).update(
        confirm_deadline=timezone.now() - timedelta(minutes=1)
    )
    api = pro_api(api_client, world["pro"])
    assert api.get(reverse("pro-bookings")).json()["results"] == []
    assert api.post(reverse("pro-booking-confirm", args=[booked.public_id])).status_code == 404
