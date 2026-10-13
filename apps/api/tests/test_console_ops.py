"""Console, lot 1 : actions de l'équipe sur les demandes, pros, clients, avis, messages, litiges.

Chaque action est journalisée ; les règles de confiance du parcours restent dans jobs.services.
"""

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from jeflink.accounts.models import ContactMessage, ProProfile, User
from jeflink.catalog.models import Trade, Zone
from jeflink.console.models import AuditLog
from jeflink.jobs import services
from jeflink.jobs.models import Dispute, Review, ServiceRequest

pytestmark = pytest.mark.django_db
PASSWORD = "un-mot-de-passe-solide"


def as_user(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def actions():
    return list(AuditLog.objects.order_by("id").values_list("action", flat=True))


@pytest.fixture
def world():
    """Un client, un pro vérifié, un pro en attente, une mission terminée et notée 1/5."""
    trade = Trade.objects.create(slug="plomberie", name="Plomberie")
    zone = Zone.objects.create(slug="ouakam", name="Ouakam")
    staff = User.objects.create_user("equipe@jeflink.local", PASSWORD, is_staff=True)
    client = User.objects.create_user("awa@example.com", PASSWORD, first_name="Awa")
    pro = User.objects.create_user("pro@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=pro, is_verified=True).trades.add(trade)
    waiting = User.objects.create_user("nouveau@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=waiting).trades.add(trade)
    req = services.create_request(client, trade=trade, zone=zone, title="Fuite", description="…")
    quote = services.submit_quote(pro, req, 15000)
    services.accept_quote(client, req, quote.pk)
    services.complete(client, req)
    services.leave_review(client, req, 1, "Pas venu, travail bâclé.")
    return {
        "staff": staff,
        "client": client,
        "pro": pro,
        "waiting": waiting,
        "req": req,
        "trade": trade,
        "zone": zone,
    }


# --- Annulation demandée par le client --------------------------------------------------------


def test_annulation_client_attend_le_rappel_du_support(world):
    from jeflink.console import finance

    client, pro = world["client"], world["pro"]
    req = services.create_request(
        client, trade=world["trade"], zone=world["zone"], title="Clim", description="…"
    )
    services.accept_quote(client, req, services.submit_quote(pro, req, 20000).pk)
    awa, staff = as_user(client), as_user(world["staff"])
    url = f"/api/requests/{req.pk}/cancel/"

    # Motif obligatoire ; « Autre » demande une précision.
    assert awa.post(url, {}, format="json").status_code == 400
    assert awa.post(url, {"reason": "other"}, format="json").status_code == 400
    res = awa.post(url, {"reason": "other_pro"}, format="json")
    assert res.status_code == 200 and res.data["status"] == "cancelling"
    assert res.data["cancellation"]["reason_label"] == "J'ai trouvé quelqu'un d'autre"

    # Le pro voit le statut, ni le motif ni rien dans l'historique.
    seen = as_user(pro).get(f"/api/requests/{req.pk}/").data
    assert seen["status"] == "cancelling" and seen["cancellation"] is None
    assert not any("autre" in e["note"] for e in seen["events"])
    # En attendant : ni fin de mission, ni seconde annulation ; l'argent reste compté.
    assert awa.post(f"/api/requests/{req.pk}/complete/").status_code == 400
    assert awa.post(url, {"reason": "price"}, format="json").status_code == 400
    assert finance.missions().filter(pk=req.pk).exists()

    # Le support rappelle : la note de l'appel est obligatoire, la mission est maintenue.
    keep = f"/api/console/requests/{req.pk}/keep/"
    assert staff.post(keep, {"note": " "}, format="json").status_code == 400
    res = staff.post(keep, {"note": "Client rassuré, le pro passe demain."}, format="json")
    assert res.status_code == 200 and res.data["status"] == "booked"

    # Nouvelle demande d'annulation, confirmée cette fois : la mission sort des comptes.
    awa.post(url, {"reason": "price"}, format="json")
    confirm = f"/api/console/requests/{req.pk}/confirm-cancel/"
    res = staff.post(confirm, {"note": "Trop cher, il a vu un voisin."}, format="json")
    assert res.status_code == 200 and res.data["status"] == "cancelled"
    assert not finance.missions().filter(pk=req.pk).exists()
    assert staff.post(confirm, {"note": "bis"}, format="json").status_code == 400
    assert actions()[-2:] == ["request.cancel_keep", "request.cancel_confirm"]
    # Réservée deux fois (avant et après le maintien), comptée une seule fois dans les chiffres.
    assert finance.first_bookings().filter(request_id=req.pk).count() == 1


# --- Tri des listes ----------------------------------------------------------------------------


def test_tri_des_listes_pris_dans_une_liste_blanche(world):
    staff = as_user(world["staff"])
    done, waiting_req = (
        world["req"],
        services.create_request(
            world["client"], trade=world["trade"], zone=world["zone"], title="WC", description="…"
        ),
    )

    def ids(url):
        res = staff.get(url)
        assert res.status_code == 200
        return [row["id"] for row in res.data["results"]]

    assert ids("/api/console/requests/") == [waiting_req.pk, done.pk]
    assert ids("/api/console/requests/?sort=oldest") == [done.pk, waiting_req.pk]
    # Montant : les demandes sans devis accepté passent après.
    assert ids("/api/console/requests/?sort=amount") == [done.pk, waiting_req.pk]
    # Valeur inconnue ou champ arbitraire : tri par défaut, jamais d'erreur.
    assert ids("/api/console/requests/?sort=-client__password") == [waiting_req.pk, done.pk]

    world["pro"].first_name = "Moussa"
    world["pro"].save()
    idle = User.objects.create_user(
        "aaa@example.com", PASSWORD, role=User.Role.PRO, first_name="Aaa"
    )
    ProProfile.objects.create(user=idle, is_verified=True)
    pros = "/api/console/pros/?status=verified"
    names = staff.get(pros).data["results"]
    assert names[0]["account"]["id"] == idle.pk
    busiest = staff.get(pros + "&sort=missions").data["results"]
    assert busiest[0]["account"]["id"] == world["pro"].pk


# --- Pros --------------------------------------------------------------------------------------


def test_verifier_un_pro_lui_permet_de_chiffrer(world):
    staff, waiting = world["staff"], world["waiting"]
    req = services.create_request(
        world["client"], trade=world["trade"], zone=world["zone"], title="WC", description="…"
    )
    assert (
        as_user(waiting).post(f"/api/requests/{req.pk}/quotes/", {"amount": 5000}).status_code
        == 403
    )

    res = as_user(staff).post(f"/api/console/pros/{waiting.pk}/verify/")
    assert res.status_code == 200 and res.data["is_verified"] is True
    assert (
        as_user(waiting).post(f"/api/requests/{req.pk}/quotes/", {"amount": 5000}).status_code
        == 201
    )
    assert actions() == ["pro.verify"]


def test_refus_de_verification_motif_visible_du_pro(world):
    staff, pro = world["staff"], world["pro"]
    url = f"/api/console/pros/{pro.pk}/reject/"
    assert as_user(staff).post(url, {"reason": ""}).status_code == 400  # motif obligatoire
    res = as_user(staff).post(url, {"reason": "Pièce d'identité illisible"})
    assert res.status_code == 200 and res.data["is_verified"] is False
    me = as_user(pro).get("/api/auth/me/").data
    assert me["pro_profile"]["verification_note"] == "Pièce d'identité illisible"


def test_file_de_verification_et_compteurs(world):
    res = as_user(world["staff"]).get("/api/console/pros/?status=pending")
    assert [p["account"]["email"] for p in res.data["results"]] == ["nouveau@example.com"]
    assert res.data["facets"] == {"pending": 1, "verified": 1, "suspended": 0}


def test_fiche_pro(world):
    res = as_user(world["staff"]).get(f"/api/console/pros/{world['pro'].pk}/")
    assert res.data["stats"] == {"quotes_sent": 1, "quotes_accepted": 1, "volume": 15000}
    assert res.data["missions"][0]["amount"] == 15000
    assert res.data["reviews"][0]["rating"] == 1


# --- Comptes -----------------------------------------------------------------------------------


def test_suspendre_un_client_coupe_sa_session(world):
    staff, client = world["staff"], world["client"]
    api = as_user(client)
    assert api.get("/api/auth/me/").status_code == 200

    res = as_user(staff).post(f"/api/console/clients/{client.pk}/suspend/", {"reason": "Abus"})
    assert res.status_code == 200 and res.data["is_active"] is False
    assert api.get("/api/auth/me/").status_code == 401  # jeton révoqué
    login = APIClient().post(
        "/api/auth/login/", {"email": client.email, "password": PASSWORD}, format="json"
    )
    assert login.status_code == 400

    as_user(staff).post(f"/api/console/clients/{client.pk}/reactivate/")
    client.refresh_from_db()
    assert client.is_active and client.suspension_reason == ""
    assert actions() == ["user.suspend", "user.reactivate"]


def test_un_compte_equipe_ne_se_suspend_pas(world):
    other = User.objects.create_user("autre@jeflink.local", PASSWORD, is_staff=True)
    # Un membre de l'équipe n'est ni client ni pro dans la console : introuvable.
    url = f"/api/console/clients/{other.pk}/suspend/"
    assert as_user(world["staff"]).post(url, {"reason": "x"}).status_code == 404


def test_liste_clients_depenses(world):
    res = as_user(world["staff"]).get("/api/console/clients/?q=awa")
    row = res.data["results"][0]
    assert (row["requests_count"], row["spent"]) == (1, 15000)


# --- Demandes ----------------------------------------------------------------------------------


def test_annulation_par_l_equipe_motif_obligatoire_et_journalise(world):
    staff = world["staff"]
    req = services.create_request(
        world["client"], trade=world["trade"], zone=world["zone"], title="Doublon", description="…"
    )
    url = f"/api/console/requests/{req.pk}/cancel/"
    assert as_user(staff).post(url, {"reason": " "}).status_code == 400
    res = as_user(staff).post(url, {"reason": "Doublon de la #1"})
    assert res.data["status"] == "cancelled"
    assert res.data["events"][-1]["note"] == "Annulée par l'équipe : Doublon de la #1"
    assert as_user(staff).post(url, {"reason": "encore"}).status_code == 400  # déjà annulée
    assert actions() == ["request.cancel"]


def test_note_interne_invisible_du_client(world):
    staff, req = world["staff"], world["req"]
    as_user(staff).post(f"/api/console/requests/{req.pk}/note/", {"note": "Client rappelé"})
    assert ServiceRequest.objects.get(pk=req.pk).staff_note == "Client rappelé"
    assert "staff_note" not in as_user(world["client"]).get(f"/api/requests/{req.pk}/").data


def test_liste_des_demandes_filtres(world):
    staff = world["staff"]
    api = as_user(staff)
    assert api.get("/api/console/requests/?status=done").data["count"] == 1
    assert api.get("/api/console/requests/?status=open").data["count"] == 0
    assert api.get(f"/api/console/requests/?q=%23{world['req'].pk}").data["count"] == 1
    assert api.get("/api/console/requests/?q=awa").data["results"][0]["amount"] == 15000
    assert api.get("/api/console/requests/").data["facets"] == {"done": 1}


# --- Litiges -----------------------------------------------------------------------------------


def test_le_client_signale_un_probleme(world):
    client, req = world["client"], world["req"]
    url = f"/api/requests/{req.pk}/report/"
    assert "report" in as_user(client).get(f"/api/requests/{req.pk}/").data["actions"]
    res = as_user(client).post(url, {"reason": "quality", "description": "Ça refuit."})
    assert res.status_code == 201
    assert res.data["dispute"]["status"] == "open"
    assert "report" not in res.data["actions"]
    # Un seul litige actif à la fois.
    assert as_user(client).post(url, {"reason": "other", "description": "…"}).status_code == 400


def test_un_tiers_ne_signale_pas(world):
    other = User.objects.create_user("autre@example.com", PASSWORD)
    url = f"/api/requests/{world['req'].pk}/report/"
    res = as_user(other).post(url, {"reason": "quality", "description": "…"})
    assert res.status_code == 404  # demande invisible pour lui


def test_pas_de_litige_sur_une_demande_ouverte(world):
    req = services.create_request(
        world["client"], trade=world["trade"], zone=world["zone"], title="WC", description="…"
    )
    with pytest.raises(Exception, match="réservée ou terminée"):
        services.open_dispute(world["client"], req, "quality", "…")


def test_l_equipe_tranche_un_litige(world):
    staff, req = world["staff"], world["req"]
    dispute = services.open_dispute(world["client"], req, "quality", "Ça refuit.")
    url = f"/api/console/disputes/{dispute.pk}/status/"
    api = as_user(staff)
    assert api.post(url, {"status": "investigating"}).data["status"] == "investigating"
    assert api.post(url, {"status": "resolved"}).status_code == 400  # décision obligatoire
    res = api.post(url, {"status": "resolved", "resolution": "Le pro repasse gratuitement."})
    assert res.data["status"] == "resolved" and res.data["closed_at"]
    assert api.post(url, {"status": "investigating"}).status_code == 400  # clos
    # Le client voit la décision dans sa demande.
    seen = as_user(world["client"]).get(f"/api/requests/{req.pk}/").data["dispute"]
    assert seen["resolution"] == "Le pro repasse gratuitement."
    assert actions() == ["dispute.update", "dispute.update"]
    assert Dispute.objects.get().handled_by == staff


# --- Avis et messages --------------------------------------------------------------------------


def test_masquer_un_avis_le_retire_du_site_et_de_la_note(world):
    staff, pro = world["staff"], world["pro"]
    review = Review.objects.get()
    assert APIClient().get("/api/reviews/").data[0]["rating"] == 1
    assert pro.pro_profile.rating()["count"] == 1

    url = f"/api/console/reviews/{review.pk}/hide/"
    assert as_user(staff).post(url, {"reason": ""}).status_code == 400
    assert as_user(staff).post(url, {"reason": "Insultes"}).data["is_hidden"] is True
    assert APIClient().get("/api/reviews/").data == []
    assert pro.pro_profile.rating() == {"average": None, "count": 0}

    as_user(staff).post(f"/api/console/reviews/{review.pk}/show/")
    assert pro.pro_profile.rating()["count"] == 1
    assert actions() == ["review.hide", "review.show"]


def test_traiter_un_message_de_contact(world):
    staff = world["staff"]
    message = ContactMessage.objects.create(name="Mbaye", email="m@example.com", message="…")
    res = as_user(staff).post(f"/api/console/messages/{message.pk}/handle/")
    assert res.data["is_handled"] is True and res.data["handled_by"]["id"] == staff.pk
    assert as_user(staff).get("/api/console/messages/?handled=0").data["count"] == 0


# --- Journal et accès --------------------------------------------------------------------------


def test_journal_d_audit(world):
    staff = world["staff"]
    as_user(staff).post(f"/api/console/pros/{world['waiting'].pk}/verify/")
    rows = as_user(staff).get("/api/console/audit/").data["results"]
    assert rows[0]["action_label"] == "Pro vérifié"
    assert rows[0]["actor"]["id"] == staff.pk


@pytest.mark.parametrize(
    "method,url",
    [
        ("get", "/api/console/requests/"),
        ("get", "/api/console/pros/"),
        ("get", "/api/console/clients/"),
        ("get", "/api/console/reviews/"),
        ("get", "/api/console/messages/"),
        ("get", "/api/console/disputes/"),
        ("get", "/api/console/audit/"),
        ("post", "/api/console/pros/1/verify/"),
    ],
)
def test_console_reservee_a_l_equipe(world, method, url):
    assert getattr(as_user(world["pro"]), method)(url).status_code == 403
    assert getattr(as_user(world["client"]), method)(url).status_code == 403


# --- Confiance après suspension ou refus -------------------------------------------------------


def _open_with_quote(world):
    req = services.create_request(
        world["client"], trade=world["trade"], zone=world["zone"], title="WC", description="…"
    )
    return req, services.submit_quote(world["pro"], req, 8000)


def test_un_pro_suspendu_n_est_plus_reservable(world):
    req, quote = _open_with_quote(world)
    as_user(world["staff"]).post(
        f"/api/console/pros/{world['pro'].pk}/suspend/", {"reason": "Litiges répétés"}
    )
    quote.refresh_from_db()
    assert quote.status == "declined"  # devis en attente retirés
    res = as_user(world["client"]).post(f"/api/requests/{req.pk}/accept/", {"quote_id": quote.pk})
    assert res.status_code == 400
    assert ServiceRequest.objects.get(pk=req.pk).pro is None  # aucun numéro échangé


def test_un_pro_de_verifie_n_est_plus_reservable(world):
    req, quote = _open_with_quote(world)
    ProProfile.objects.filter(user=world["pro"]).update(is_verified=False)
    res = as_user(world["client"]).post(f"/api/requests/{req.pk}/accept/", {"quote_id": quote.pk})
    assert res.status_code == 400


def test_demandes_d_un_client_suspendu_masquees_aux_pros(world):
    req = services.create_request(
        world["client"], trade=world["trade"], zone=world["zone"], title="WC", description="…"
    )
    as_user(world["staff"]).post(
        f"/api/console/clients/{world['client'].pk}/suspend/", {"reason": "Abus"}
    )
    assert req not in services.open_requests_for_pro(world["pro"])
    res = as_user(world["pro"]).post(f"/api/requests/{req.pk}/quotes/", {"amount": 5000})
    assert res.status_code in (400, 404)


def test_un_pro_non_retenu_ne_voit_pas_le_litige(world):
    req, _ = _open_with_quote(world)
    other = User.objects.create_user("autre-pro@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=other, is_verified=True).trades.add(world["trade"])
    services.submit_quote(other, req, 9000)
    services.accept_quote(world["client"], req, req.quotes.get(pro=world["pro"]).pk)
    services.open_dispute(world["client"], req, "quality", "…")
    api = as_user(other)
    assert api.get(f"/api/requests/{req.pk}/").data["dispute"] is None
    res = api.post(f"/api/requests/{req.pk}/report/", {"reason": "other", "description": "…"})
    assert res.status_code == 403


def test_l_equipe_ouvre_un_litige_par_la_console_seulement(world):
    url = f"/api/requests/{world['req'].pk}/report/"
    res = as_user(world["staff"]).post(url, {"reason": "other", "description": "…"})
    assert res.status_code == 403


def test_le_journal_ne_se_modifie_pas(world):
    api = as_user(world["staff"])
    assert api.post("/api/console/audit/", {}).status_code == 405
    assert api.delete("/api/console/audit/1/").status_code in (404, 405)
