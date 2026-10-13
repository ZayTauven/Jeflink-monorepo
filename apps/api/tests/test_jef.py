"""Lot 4 : Jef, l'assistant de réservation (mode guidé sans clé, mode IA simulé)."""

from types import SimpleNamespace

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from jeflink.accounts.models import ProProfile, User
from jeflink.catalog.models import Trade, Zone
from jeflink.console.models import PlatformSettings
from jeflink.jef import ai
from jeflink.jef.models import JefSession

pytestmark = pytest.mark.django_db
PASSWORD = "un-mot-de-passe-solide"


def as_user(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def world():
    plomberie = Trade.objects.create(slug="plomberie", name="Plomberie")
    Trade.objects.create(slug="electricite", name="Électricité")
    zone = Zone.objects.create(slug="ouakam", name="Ouakam")
    client = User.objects.create_user("awa@example.com", PASSWORD)
    other = User.objects.create_user("binta@example.com", PASSWORD)
    pro = User.objects.create_user("pro@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=pro, is_verified=True).trades.add(plomberie)
    ops = User.objects.create_user("ops@jeflink.local", PASSWORD, is_staff=True, staff_role="ops")
    marketing = User.objects.create_user(
        "mk@jeflink.local", PASSWORD, is_staff=True, staff_role="marketing"
    )
    return {"zone": zone, "client": client, "other": other, "pro": pro, "ops": ops, "mk": marketing}


TEXT = "Fuite sous l'évier de la cuisine depuis ce matin, l'eau coule beaucoup."


def start(world, text=TEXT, trade=""):
    return as_user(world["client"]).post("/api/jef/", {"text": text, "trade": trade})


# --- Mode guidé (sans clé) --------------------------------------------------------------------


def test_mode_guide_devine_le_metier_et_pose_trois_questions(world):
    res = start(world)
    assert res.status_code == 201
    assert res.data["mode"] == "guide"
    assert res.data["trade"] == {"slug": "plomberie", "name": "Plomberie"}
    assert [q["id"] for q in res.data["questions"]] == ["q1", "q2", "q3", "q9"]
    assert "urgent" not in res.data["questions"][2]  # règle interne, pas envoyée au client


def test_la_fiche_reprend_les_reponses_et_suit_la_demande(world):
    session = start(world).data
    res = as_user(world["client"]).post(
        f"/api/jef/{session['id']}/brief/",
        {
            "answers": {
                "q1": "Fuite d'eau",
                "q3": "Oui, ça coule beaucoup ou ça déborde",
                "zzz": "ignoré",
            }
        },
        format="json",
    )
    brief = res.data["brief"]
    assert res.status_code == 200 and brief["urgent"] is True
    assert brief["title"].startswith("Fuite sous l'évier")
    assert "Que se passe-t-il ? Fuite d'eau" in brief["description"]
    assert set(res.data["answers"]) == {"q1", "q3"}
    assert brief["client_tips"] and brief["pro_bring"]

    # Publiée avec la demande : le pro du métier lit la fiche.
    req = as_user(world["client"]).post(
        "/api/requests/",
        {
            "trade": "plomberie",
            "zone": "ouakam",
            "title": brief["title"],
            "description": brief["description"],
            "jef_session": session["id"],
        },
    )
    mine = req.data["jef"]
    assert req.status_code == 201 and mine["mode"] == "guide" and mine["client_tips"]
    assert "pro_bring" not in mine
    # Le pro lit la fiche, sans les conseils au client ni la version proposée par Jef.
    seen = as_user(world["pro"]).get(f"/api/requests/{req.data['id']}/").data["jef"]
    assert seen["pro_details"][0] == "Que se passe-t-il ? Fuite d'eau" and seen["urgent"]
    assert "client_tips" not in seen and "description" not in seen


def test_une_fiche_ne_se_joint_qu_a_son_auteur(world):
    session = start(world).data
    as_user(world["client"]).post(f"/api/jef/{session['id']}/brief/", {}, format="json")
    other = as_user(world["other"])
    assert other.post(f"/api/jef/{session['id']}/brief/", {}, format="json").status_code == 404
    req = other.post(
        "/api/requests/",
        {
            "trade": "plomberie",
            "zone": "ouakam",
            "title": "Fuite",
            "description": "…",
            "jef_session": session["id"],
        },
    )
    assert req.status_code == 201 and req.data["jef"] is None
    assert JefSession.objects.get(pk=session["id"]).request is None


def test_jef_reserve_aux_clients_en_service_et_limite(world, settings):
    assert as_user(world["pro"]).post("/api/jef/", {"text": TEXT}).status_code == 403
    assert start(world, text="fuite").status_code == 400  # trop court
    PlatformSettings.objects.update(jef_enabled=False)
    assert start(world).status_code == 400
    PlatformSettings.objects.update(jef_enabled=True)
    settings.JEF_DAILY_LIMIT = 2
    assert start(world).status_code == 201 and start(world).status_code == 201
    assert "beaucoup utilisé" in str(start(world).data)


def test_jef_refuse_les_coordonnees_et_signale_le_danger(world):
    res = start(world, text="Fuite chez moi, appelez-moi au 77 123 45 67 svp")
    assert res.status_code == 400 and "numéro" in str(res.data)
    res = start(world, text="La prise du salon fait des étincelles et sent le brûlé")
    assert res.data["trade"]["slug"] == "electricite" and res.data["safety"]


def test_jef_ne_devine_pas_en_cas_de_doute(world):
    res = start(world, text="Il manque du gaz dans ma clim, elle ne refroidit plus")
    assert res.data["safety"] == []  # « gaz » seul n'est pas un danger
    assert start(world, text="Quelque chose ne va pas à la maison").data["trade"] is None


# --- Mode IA (Claude simulé) ------------------------------------------------------------------


def test_mode_ia_nettoie_les_reponses_du_modele(world, settings, monkeypatch):
    settings.ANTHROPIC_API_KEY = "cle-de-test"
    answers = {
        "questions": {
            "trade": "electricite",
            "urgent": False,
            "questions": [
                {"question": "La prise est-elle chaude ?", "choices": ["Oui", "Non"]},
                {"question": "  ", "choices": []},  # vide : écartée
                {"question": "Q2", "choices": ["a"] * 9},
                {"question": "Q3", "choices": []},
                {"question": "Q4 en trop", "choices": []},
            ],
        },
        "brief": {
            "title": "Prise qui chauffe " * 20,
            "description": "La prise du salon chauffe.",
            "urgent": True,
            "client_tips": ["Coupez le disjoncteur."] * 5,
            "pro_summary": "Prise chaude au salon.",
            "pro_details": ["Salon"],
            "pro_bring": ["Prise de rechange"],
        },
    }
    calls = []

    def fake_ask(content, output_format, **kwargs):
        calls.append(content)
        props = output_format["schema"]["properties"]
        return answers["questions"] if "questions" in props else answers["brief"]

    monkeypatch.setattr(ai, "_ask", fake_ask)
    res = start(world, text="Ma prise du salon chauffe et sent un peu le plastique.")
    assert res.data["mode"] == "ai" and res.data["trade"]["slug"] == "electricite"
    assert [q["id"] for q in res.data["questions"]] == ["q1", "q2", "q3"]  # 3 au plus
    assert len(res.data["questions"][1]["choices"]) == 6
    assert "<description_client>" in calls[0]  # le texte du client est encadré comme donnée

    brief = (
        as_user(world["client"])
        .post(f"/api/jef/{res.data['id']}/brief/", {"answers": {"q1": "Oui"}}, format="json")
        .data["brief"]
    )
    assert len(brief["title"]) <= 120 and len(brief["client_tips"]) == 3
    assert "La prise est-elle chaude ? Oui" in calls[1]
    # Un nouvel envoi ne rappelle pas l'IA : la fiche déjà prête est renvoyée.
    again = as_user(world["client"]).post(
        f"/api/jef/{res.data['id']}/brief/", {"answers": {"q1": "Non"}}, format="json"
    )
    assert again.data["brief"] == brief and len(calls) == 2


def test_si_l_ia_ne_repond_pas_jef_passe_en_mode_guide(world, settings, monkeypatch):
    settings.ANTHROPIC_API_KEY = "cle-de-test"

    def down(*args, **kwargs):
        raise ai.JefUnavailable("réseau")

    monkeypatch.setattr(ai, "_ask", down)
    res = start(world)
    assert res.status_code == 201 and res.data["mode"] == "guide"
    assert res.data["trade"]["slug"] == "plomberie"


class FakeAnthropic:
    """Remplace le client du SDK : on vérifie la requête envoyée et la lecture de la réponse."""

    last: dict = {}
    reply = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text='{"ok": true}')],
    )

    def __init__(self, **kwargs):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        FakeAnthropic.last = kwargs
        return FakeAnthropic.reply


def test_requete_envoyee_a_claude(settings, monkeypatch):
    settings.ANTHROPIC_API_KEY = "cle-de-test"
    settings.JEF_MODEL = "claude-opus-5-5"
    monkeypatch.setattr(ai.anthropic, "Anthropic", FakeAnthropic)
    assert ai._ask("bonjour", {"type": "json_schema", "schema": {}}) == {"ok": True}
    sent = FakeAnthropic.last
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"
    assert sent["output_config"]["effort"] == "low"
    assert "thinking" not in sent  # adaptatif par défaut sur ce modèle

    FakeAnthropic.reply = SimpleNamespace(stop_reason="refusal", content=[])
    with pytest.raises(ai.JefUnavailable):
        ai._ask("bonjour", {"type": "json_schema", "schema": {}})


# --- Console ------------------------------------------------------------------------------------


def test_console_relit_les_echanges_sans_exposer_la_cle(world, settings):
    start(world)
    settings.ANTHROPIC_API_KEY = "cle-secrete-de-test"
    res = as_user(world["ops"]).get("/api/console/jef/")
    assert res.status_code == 200
    assert res.data["status"]["ai"] is True and res.data["stats"]["sessions"] == 1
    assert res.data["results"][0]["text"] == TEXT
    assert "cle-secrete-de-test" not in str(res.data)
    assert as_user(world["mk"]).get("/api/console/jef/").status_code == 403


def test_coordonnees_masquees_dans_la_fiche_de_l_ia(world, settings, monkeypatch):
    settings.ANTHROPIC_API_KEY = "cle-de-test"

    def fake_ask(content, output_format, **kwargs):
        if "questions" in output_format["schema"]["properties"]:
            return {"trade": "plomberie", "urgent": False, "questions": []}
        return {
            "title": "Fuite",
            "description": "Fuite. Écrivez-moi sur WhatsApp au +221 77 123 45 67.",
            "urgent": False,
            "client_tips": [],
            "pro_summary": "Voir https://exemple.test ou client@exemple.test",
            "pro_details": [],
            "pro_bring": [],
        }

    monkeypatch.setattr(ai, "_ask", fake_ask)
    session = start(world).data
    brief = (
        as_user(world["client"])
        .post(f"/api/jef/{session['id']}/brief/", {}, format="json")
        .data["brief"]
    )
    assert "77 123" not in brief["description"] and "[masqué]" in brief["description"]
    assert brief["pro_summary"] == "Voir [masqué] ou [masqué]"


def test_plafond_global_de_l_ia(world, settings, monkeypatch):
    settings.ANTHROPIC_API_KEY = "cle-de-test"
    settings.JEF_AI_DAILY_LIMIT = 0
    monkeypatch.setattr(ai, "_ask", lambda *a, **k: pytest.fail("l'IA ne doit pas être appelée"))
    assert start(world).data["mode"] == "guide"
