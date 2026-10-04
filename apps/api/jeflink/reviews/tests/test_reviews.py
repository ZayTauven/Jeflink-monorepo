"""Avis (spec 004, tâche 8) : dépôt, délais, publication à la clôture, moyenne, modération,
anonymiseur, API et note sur les devis."""

import logging
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings import services as booking_services
from jeflink.bookings.machine import Status
from jeflink.bookings.models import Booking
from jeflink.bookings.tests.factories import advance, make_scene, scheduled
from jeflink.bookings.tests.test_services import expect
from jeflink.providers.models import Provider
from jeflink.requests.tests.test_requests_api import bearer
from jeflink.reviews import selectors, services
from jeflink.reviews.models import Review
from jeflink.trust.models import AuditEvent, Dispute

pytestmark = pytest.mark.django_db


def completed():
    scene, booking = scheduled()
    return scene, advance(booking, Status.COMPLETED)


def close(booking):
    Booking.objects.filter(pk=booking.pk).update(
        dispute_deadline=timezone.now() - timedelta(minutes=1)
    )
    assert booking_services.close_due() >= 1
    booking.refresh_from_db()
    return booking


def rate(scene, booking, rating=5, tags=(), comment=""):
    return services.submit_review(
        booking=booking, actor=scene.client, rating=rating, tags=list(tags), comment=comment
    )


# --- Dépôt -------------------------------------------------------------------------------------


def test_une_note_seule_suffit():
    scene, booking = completed()
    result = rate(scene, booking, 4)
    review = result.review
    assert result.created and (review.rating, review.tags, review.comment) == (4, [], "")
    assert review.provider_id == booking.provider_id and review.author == scene.client
    assert review.published_at is None  # publié à la clôture seulement
    audit = AuditEvent.objects.get(action="reviews.review.submitted")
    assert audit.metadata == {"rating": 4, "edited": False}


def test_puces_et_commentaire_facultatifs_espaces_normalises():
    scene, booking = completed()
    review = rate(scene, booking, 5, ["on_time", "clean", "on_time"], "  Très   bien\n").review
    assert review.tags == ["on_time", "clean"] and review.comment == "Très bien"
    assert "bien" not in str(AuditEvent.objects.get(action="reviews.review.submitted").metadata)


@pytest.mark.parametrize(
    ("rating", "tags", "comment"),
    [
        (0, [], ""),
        (6, [], ""),
        (True, [], ""),
        ("5", [], ""),
        (4, ["late"], ""),  # une puce négative n'existe que sous 3 étoiles
        (5, ["inconnue"], ""),
        (2, ["pas_une_puce"], ""),
        (5, [], "x" * 501),
    ],
)
def test_avis_invalide(rating, tags, comment):
    scene, booking = completed()
    with expect("review_invalid", 422):
        services.submit_review(
            booking=booking, actor=scene.client, rating=rating, tags=tags, comment=comment
        )
    assert not Review.objects.exists()


def test_puces_negatives_sous_trois_etoiles():
    scene, booking = completed()
    review = rate(scene, booking, 2, ["late", "messy", "quality"]).review
    assert review.tags == ["late", "messy", "quality"]


def test_modifier_son_avis_dans_le_delai():
    scene, booking = completed()
    first = rate(scene, booking, 3, comment="Moyen").review
    again = rate(scene, booking, 5, ["quality"], "Finalement très bien")
    assert not again.created and again.review.pk == first.pk and Review.objects.count() == 1
    again.review.refresh_from_db()
    assert (again.review.rating, again.review.edited_at is not None) == (5, True)
    assert AuditEvent.objects.filter(action="reviews.review.submitted").count() == 2


@pytest.mark.parametrize(
    "status", [Status.ACCEPTED, Status.SCHEDULED, Status.IN_PROGRESS, Status.CANCELLED]
)
def test_pas_d_avis_sans_reservation_terminee(status):
    scene, booking = scheduled()
    Booking.objects.filter(pk=booking.pk).update(
        status=status, cancelled_by="system" if status == Status.CANCELLED else ""
    )
    with expect("review_not_allowed"):
        rate(scene, booking)


def test_avis_refuse_a_un_autre_compte_et_au_pro():
    scene, booking = completed()
    with expect("not_found", 404):
        services.submit_review(
            booking=booking, actor=CompleteUserFactory(), rating=5, tags=[], comment=""
        )
    with expect("not_found", 404):
        services.submit_review(
            booking=booking, actor=booking.provider.owner, rating=5, tags=[], comment=""
        )
    assert scene.client


def test_delai_de_14_jours_apres_terminaison_litige_compris(settings):
    scene, booking = completed()
    Booking.objects.filter(pk=booking.pk).update(completed_at=timezone.now() - timedelta(days=15))
    with expect("review_window_closed"):
        rate(scene, booking)
    Booking.objects.filter(pk=booking.pk).update(completed_at=timezone.now() - timedelta(days=13))
    assert rate(scene, booking).created
    settings.REVIEW_WINDOW = timedelta(days=5)
    with expect("review_window_closed"):
        rate(scene, booking)
    # Un litige ouvert ne retire pas le droit d'avis.
    scene2, other = completed()
    booking_services.open_dispute(
        booking=other, actor=scene2.client, reason="damage", description="Le travail est mal fait."
    )
    assert rate(scene2, other).created


def test_sept_jours_de_plus_apres_une_decision_en_faveur_du_client():
    scene, booking = completed()
    booking_services.open_dispute(
        booking=booking, actor=scene.client, reason="not_done", description="Rien n'a été fait."
    )
    Booking.objects.filter(pk=booking.pk).update(completed_at=timezone.now() - timedelta(days=16))
    with expect("review_window_closed"):
        rate(scene, booking)
    ops = User.objects.create_user("+221770000911", is_staff=True)
    booking_services.resolve_dispute(
        dispute=Dispute.objects.get(), decision="for_client", note="Client crédible", operator=ops
    )
    booking.refresh_from_db()
    assert selectors.review_deadline(booking) > timezone.now() + timedelta(days=6)
    assert rate(scene, booking).review.published_at is not None  # clôturée : publié tout de suite


def test_decision_en_faveur_du_pro_n_allonge_pas_le_delai():
    scene, booking = completed()
    booking_services.open_dispute(
        booking=booking, actor=scene.client, reason="price", description="Le prix a changé."
    )
    Booking.objects.filter(pk=booking.pk).update(completed_at=timezone.now() - timedelta(days=16))
    ops = User.objects.create_user("+221770000912", is_staff=True)
    booking_services.resolve_dispute(
        dispute=Dispute.objects.get(), decision="for_pro", note="Avenant accepté", operator=ops
    )
    booking.refresh_from_db()
    with expect("review_window_closed"):
        rate(scene, booking)


# --- Publication à la clôture ------------------------------------------------------------------


def test_publie_a_la_cloture_pas_avant():
    scene, booking = completed()
    review = rate(scene, booking, 5).review
    assert review.published_at is None
    close(booking)
    review.refresh_from_db()
    assert review.published_at is not None
    # Un second passage du gestionnaire ne change rien (idempotent).
    first = review.published_at
    services.publish_on_close(booking, "window_elapsed")
    review.refresh_from_db()
    assert review.published_at == first


def test_avis_depose_apres_la_cloture_publie_tout_de_suite():
    scene, booking = completed()
    booking = close(booking)
    result = rate(scene, booking, 4)
    assert result.review.published_at is not None


def test_la_cloture_ne_depend_pas_de_l_avis():
    _, booking = completed()
    assert close(booking).status == Status.CLOSED  # aucun avis déposé


def test_le_gestionnaire_est_enregistre_une_seule_fois():
    handlers = [h for h in booking_services._CLOSE_HANDLERS if h is services.publish_on_close]
    assert len(handlers) == 1


# --- Moyenne -----------------------------------------------------------------------------------


def reviewed_provider(ratings, *, provider=None, publish=True):
    """Un pro et des avis publiés (une réservation terminée par avis)."""
    provider = provider
    for rating in ratings:
        scene, booking = scheduled()
        if provider is not None:
            Booking.objects.filter(pk=booking.pk).update(provider=provider)
        else:
            provider = booking.provider
        Booking.objects.filter(pk=booking.pk).update(
            status=Status.CLOSED, completed_at=timezone.now(), closed_at=timezone.now()
        )
        booking.refresh_from_db()
        review = Review.objects.create(
            booking=booking, provider=provider, author=scene.client, rating=rating,
            published_at=timezone.now() if publish else None,
        )  # fmt: skip
        assert review.pk
    return provider


def test_moyenne_a_une_decimale_et_null_sous_trois_avis():
    provider = reviewed_provider([5, 4])
    assert selectors.rating_for_providers([provider.pk]) == {provider.pk: None}
    provider = reviewed_provider([5, 4, 4], provider=provider)  # 5 avis : 5, 4, 5, 4, 4
    assert selectors.rating_for_providers([provider.pk]) == {
        provider.pk: {"average": 4.4, "count": 5}
    }


def test_le_seuil_d_affichage_est_un_reglage(settings):
    provider = reviewed_provider([5, 3])
    settings.REVIEWS_MIN_DISPLAY = 2
    assert selectors.rating_for_providers([provider.pk])[provider.pk] == {
        "average": 4.0,
        "count": 2,
    }


def test_non_publies_masques_comptes_de_revue_et_pros_de_demo_exclus():
    provider = reviewed_provider([5, 5, 5])
    reviewed_provider([1, 1], provider=provider, publish=False)  # non publiés
    reviewed_provider([1], provider=provider)  # un avis publié, que l'on masque
    hidden = Review.objects.filter(rating=1, published_at__isnull=False).get()
    ops = User.objects.create_user("+221770000913", is_staff=True)
    assert selectors.rating_for_providers([provider.pk])[provider.pk]["average"] == 4.0
    services.hide_review(review=hidden, reason="abusive", operator=ops)
    assert selectors.rating_for_providers([provider.pk]) == {
        provider.pk: {"average": 5.0, "count": 3}
    }
    User.objects.filter(pk=Review.objects.filter(rating=5).first().author_id).update(
        is_review_account=True
    )
    assert selectors.rating_for_providers([provider.pk])[provider.pk] is None  # 2 avis restent
    Provider.objects.filter(pk=provider.pk).update(is_demo=True)
    assert selectors.rating_for_providers([provider.pk]) == {provider.pk: None}


def test_une_requete_pour_tous_les_pros(django_assert_num_queries):
    a, b = reviewed_provider([5, 5, 5]), reviewed_provider([3, 3, 3])
    with django_assert_num_queries(1):
        ratings = selectors.rating_for_providers([a.pk, b.pk, 999_999])
    assert ratings[a.pk]["average"] == 5.0 and ratings[b.pk]["average"] == 3.0
    assert ratings[999_999] is None


# --- Modération --------------------------------------------------------------------------------


def moderator(phone="+221770000914"):
    user = User.objects.create_user(phone, is_staff=True)
    user.groups.add(Group.objects.get(name="Modération avis"))
    return user


def test_masquer_et_reafficher_sans_jamais_supprimer():
    scene, booking = completed()
    review = rate(scene, booking, 1, comment="Mauvais").review
    ops = moderator()
    with expect("reason_invalid", 422):
        services.hide_review(review=review, reason="parce que", operator=ops)
    services.hide_review(review=review, reason="abusive", operator=ops)
    review.refresh_from_db()
    assert review.hidden_at and review.hidden_reason == "abusive" and review.hidden_by == ops
    audit = AuditEvent.objects.get(action="reviews.review.hidden")
    assert audit.actor_kind == "ops" and audit.metadata == {"reason": "abusive"}
    services.hide_review(review=review, reason="fake", operator=ops)  # rejeu : pas de second audit
    assert AuditEvent.objects.filter(action="reviews.review.hidden").count() == 1
    services.restore_review(review=review, operator=ops)
    review.refresh_from_db()
    assert review.hidden_at is None and review.hidden_reason == "" and Review.objects.count() == 1
    assert AuditEvent.objects.filter(action="reviews.review.restored").count() == 1


def test_admin_masquer_et_reafficher(client, monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)
    scene, booking = completed()
    review = rate(scene, booking, 1, comment="Avis litigieux").review
    ops = moderator()
    client.force_login(ops)
    url = reverse("admin:reviews_review_changelist")
    response = client.post(url, {"action": "hide", "_selected_action": [review.pk]})
    assert (
        response.status_code == 200
        and "Un avis masqué sort de la moyenne" in response.content.decode()
    )
    client.post(
        url,
        {"action": "hide", "_selected_action": [review.pk], "apply": "1", "reason": "off_topic"},
        follow=True,
    )
    review.refresh_from_db()
    assert review.hidden_at and review.hidden_by == ops
    page = client.get(reverse("admin:reviews_review_change", args=[review.pk]))
    assert page.status_code == 200 and "Avis litigieux" in page.content.decode()
    assert scene.client.phone not in page.content.decode()
    client.post(url, {"action": "restore", "_selected_action": [review.pk]}, follow=True)
    review.refresh_from_db()
    assert review.hidden_at is None


def test_admin_un_autre_groupe_ne_modere_pas(client, monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)
    scene, booking = completed()
    review = rate(scene, booking, 1).review
    user = User.objects.create_user("+221770000915", is_staff=True)
    user.groups.add(Group.objects.get(name="Validation pros"))
    client.force_login(user)
    assert client.get(reverse("admin:reviews_review_changelist")).status_code == 403
    client.post(
        reverse("admin:reviews_review_changelist"),
        {"action": "hide", "_selected_action": [review.pk], "apply": "1", "reason": "abusive"},
    )
    review.refresh_from_db()
    assert review.hidden_at is None


# --- Anonymiseur -------------------------------------------------------------------------------


def test_anonymiseur_vide_le_commentaire_detache_l_auteur_et_garde_la_note():
    scene, booking = completed()
    review = rate(scene, booking, 4, ["quality"], "Appelez-moi au 77 123 45 67").review
    services.anonymize_reviews(scene.client)
    review.refresh_from_db()
    assert (review.comment, review.author, review.rating, review.tags) == ("", None, 4, ["quality"])


# --- API ---------------------------------------------------------------------------------------


def test_api_put_avis_puis_vue_du_client_et_du_pro(api_client):
    scene, booking = completed()
    client = bearer(api_client, scene.client)
    pro = bearer(api_client, booking.provider.owner, app="pro")
    url = reverse("booking-review", args=[booking.public_id])
    detail = client.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert detail["can_review"] is True and detail["review"] is None and detail["review_deadline"]
    response = client.put(
        url,
        {"rating": 4, "tags": ["on_time"], "comment": "Rappelez au 77 123 45 67 pour la suite"},
        format="json",
    )
    data = response.json()
    assert response.status_code == 200 and data["review"]["rating"] == 4
    assert data["review"]["published"] is False and data["review"]["comment"].startswith("Rappelez")
    # Le pro ne voit rien tant que l'avis n'est pas publié.
    seen = pro.get(reverse("pro-booking-detail", args=[booking.public_id])).json()
    assert seen["review"] is None
    close(booking)
    seen = pro.get(reverse("pro-booking-detail", args=[booking.public_id])).json()
    assert seen["review"]["rating"] == 4 and seen["review"]["tags"] == ["on_time"]
    assert "77 123 45 67" not in seen["review"]["comment"] and "••••" in seen["review"]["comment"]
    # Modifier encore dans le délai.
    again = client.put(url, {"rating": 5}, format="json")
    assert again.status_code == 200 and again.json()["review"]["rating"] == 5


def test_api_erreurs_et_permissions(api_client):
    scene, booking = completed()
    client = bearer(api_client, scene.client)
    url = reverse("booking-review", args=[booking.public_id])
    for body, status, code in [
        ({"rating": 9}, 422, "review_invalid"),
        ({"rating": 5, "tags": ["late"]}, 422, "review_invalid"),
        ({"rating": 5, "comment": "x" * 600}, 422, "review_invalid"),
        ({"rating": 5, "comment": "x" * 2001}, 400, "invalid"),
        ({}, 400, "invalid"),
        ({"rating": "beaucoup"}, 400, "invalid"),
    ]:
        response = client.put(url, body, format="json")
        assert (response.status_code, response.json()["code"]) == (status, code), body
    Booking.objects.filter(pk=booking.pk).update(completed_at=timezone.now() - timedelta(days=20))
    response = client.put(url, {"rating": 5}, format="json")
    assert (response.status_code, response.json()["code"]) == (409, "review_window_closed")
    detail = client.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert detail["can_review"] is False
    other = bearer(api_client, CompleteUserFactory())
    assert other.put(url, {"rating": 5}, format="json").status_code == 404
    assert (
        bearer(api_client, booking.provider.owner, "pro")
        .put(url, {"rating": 5}, format="json")
        .status_code
        == 404
    )
    api_client.credentials()
    assert api_client.put(url, {"rating": 5}, format="json").status_code == 401
    scene2, early = scheduled()
    response = bearer(api_client, scene2.client).put(
        reverse("booking-review", args=[early.public_id]), {"rating": 5}, format="json"
    )
    assert (response.status_code, response.json()["code"]) == (409, "review_not_allowed")


def test_la_note_apparait_sur_les_devis_a_partir_de_trois_avis(api_client):
    scene = make_scene(pros=2)
    first, second = scene.providers
    reviewed_provider([5, 4, 3], provider=first)
    reviewed_provider([5, 5], provider=second)
    client = bearer(api_client, scene.client)
    detail = client.get(reverse("request-detail", args=[scene.request.public_id])).json()
    by_name = {q["provider"]["business_name"]: q["provider"]["rating"] for q in detail["quotes"]}
    assert by_name[first.business_name] == {"average": 4.0, "count": 3}
    assert by_name[second.business_name] is None  # « Nouveau sur Jeflink »


def test_la_note_est_sur_la_reservation_et_la_liste(api_client):
    scene, booking = scheduled()
    provider = reviewed_provider([5, 5, 4], provider=booking.provider)
    client = bearer(api_client, scene.client)
    detail = client.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert detail["provider"]["rating"] == {"average": 4.7, "count": 3}
    listed = client.get(reverse("bookings")).json()["results"]
    assert listed[0]["provider"]["rating"] == {"average": 4.7, "count": 3}
    via_request = client.get(reverse("request-detail", args=[scene.request.public_id])).json()
    assert via_request["booking"]["provider"]["rating"]["count"] == 3
    assert provider.pk


def test_pas_de_requete_par_pro_sur_le_detail_d_une_demande(
    api_client, django_assert_max_num_queries
):
    scene = make_scene(pros=3)
    client = bearer(api_client, scene.client)
    url = reverse("request-detail", args=[scene.request.public_id])
    client.get(url)  # chauffe les caches de session
    with django_assert_max_num_queries(40) as ctx:
        assert client.get(url).status_code == 200
    rating_queries = [q for q in ctx.captured_queries if "reviews_review" in q["sql"]]
    assert len(rating_queries) == 1


def test_les_commentaires_ne_sont_pas_journalises(caplog, api_client):
    caplog.set_level(logging.DEBUG)
    scene, booking = completed()
    bearer(api_client, scene.client).put(
        reverse("booking-review", args=[booking.public_id]),
        {"rating": 2, "comment": "COMMENTAIRE-SECRET-XYZ"},
        format="json",
    )
    assert "COMMENTAIRE-SECRET-XYZ" not in " ".join(r.getMessage() for r in caplog.records)
    dumped = str(list(AuditEvent.objects.values("action", "metadata")))
    assert "COMMENTAIRE-SECRET-XYZ" not in dumped
