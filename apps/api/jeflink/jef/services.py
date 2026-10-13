"""Règles de Jef : qui peut l'utiliser, combien de fois, et ce qu'on garde de ses réponses.

Les réponses de l'IA sont nettoyées (longueurs, nombre d'éléments, coordonnées masquées) avant
d'être stockées : la fiche est affichée au pro telle quelle, comme un texte du client.
"""

import re
from contextlib import suppress
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from jeflink.catalog.models import Trade
from jeflink.console.models import PlatformSettings

from . import ai, guide
from .models import JefSession

M = JefSession.Mode

# Coordonnées : le numéro du client n'est partagé qu'après la réservation (règle 7), et la fiche
# ne doit pas servir à contourner Jeflink (lien, email, « appelez-moi au… »).
PHONE = re.compile(r"(?:\+|00)?(?:221[\s.-]*)?[37]\d(?:[\s.-]*\d){7}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
MASK = "[masqué]"


def _mask(text: str) -> str:
    for pattern in (URL, EMAIL, PHONE):
        text = pattern.sub(MASK, text)
    return text


def _line(value, limit: int) -> str:
    return _mask(" ".join(str(value or "").split()))[:limit]


def _lines(values, count: int, limit: int) -> list[str]:
    items = values if isinstance(values, list) else []
    return [line for v in items[:count] if (line := _line(v, limit))]


def _clean_questions(raw) -> list[dict]:
    """Trois questions au plus, non vides, numérotées q1… ; six choix courts au plus."""
    kept = [
        (text, q.get("choices"))
        for q in (raw if isinstance(raw, list) else [])
        if isinstance(q, dict) and (text := _line(q.get("question"), 160))
    ][:3]
    return [
        {"id": f"q{i}", "question": text, "choices": _lines(choices, 6, 60)}
        for i, (text, choices) in enumerate(kept, start=1)
    ]


def _clean_brief(raw: dict) -> dict:
    return {
        "title": _line(raw.get("title"), 120),
        "description": _mask(str(raw.get("description") or "").strip())[:1500],
        "urgent": bool(raw.get("urgent")),
        "client_tips": _lines(raw.get("client_tips"), 3, 220),
        "pro_summary": _line(raw.get("pro_summary"), 300),
        "pro_details": _lines(raw.get("pro_details"), 8, 200),
        "pro_bring": _lines(raw.get("pro_bring"), 6, 120),
    }


def available() -> bool:
    return PlatformSettings.load().jef_enabled


def _ai_allowed() -> bool:
    """Plafond global d'appels à l'IA sur 24 h (comptes multiples) : au-delà, mode guidé."""
    since = timezone.now() - timedelta(days=1)
    used = JefSession.objects.filter(mode=M.AI, created_at__gte=since).count()
    return ai.enabled() and used < settings.JEF_AI_DAILY_LIMIT


def safety(session: JefSession) -> list[str]:
    """Gestes de sécurité à montrer dès les questions, si le texte décrit un danger."""
    return guide.safety_tips(session.text, session.trade.slug if session.trade else "")


def start(client, text: str, trade_slug: str = "") -> JefSession:
    """Le client décrit son souci : Jef propose un métier et pose ses questions."""
    if client.is_pro:
        raise PermissionDenied("Jef aide les clients à décrire leur demande.")
    if not available():
        raise ValidationError("Jef est en pause. Remplissez le formulaire directement.")
    text = text.strip()
    if len(text) < 10:
        raise ValidationError({"text": "Dites-en un peu plus : quelques mots sur ce qui se passe."})
    if PHONE.search(text) or EMAIL.search(text):
        raise ValidationError(
            {"text": "Retirez votre numéro ou votre email : le pro les reçoit à la réservation."}
        )
    since = timezone.now() - timedelta(days=1)
    if client.jef_sessions.filter(created_at__gte=since).count() >= settings.JEF_DAILY_LIMIT:
        raise ValidationError(
            "Vous avez beaucoup utilisé Jef aujourd'hui. Remplissez le formulaire directement."
        )
    trades = dict(Trade.objects.filter(is_active=True).values_list("slug", "name"))
    chosen = trade_slug if trade_slug in trades else ""
    try:
        if not _ai_allowed():
            raise ai.JefUnavailable("pas d'IA")
        raw = ai.questions(text, trades, chosen)
        suggested = raw.get("trade") if raw.get("trade") in trades else ""
        mode, qs = M.AI, _clean_questions(raw.get("questions"))
    except ai.JefUnavailable:
        suggested = guide.guess_trade(text, list(trades))
        mode, qs = M.GUIDE, []
    slug = chosen or suggested
    if not qs:  # mode guidé, ou IA sans question exploitable
        qs = guide.questions(slug)
    return JefSession.objects.create(
        client=client,
        trade=Trade.objects.filter(slug=slug).first() if slug else None,
        text=text[:2000],
        mode=mode,
        questions=qs,
    )


def write_brief(client, session: JefSession, answers: dict) -> JefSession:
    """Le client a répondu : Jef rédige la demande et la fiche du pro."""
    if session.client_id != client.pk:
        raise PermissionDenied("Cet échange avec Jef ne vous appartient pas.")
    if session.request_id:
        raise ValidationError("Cette fiche est déjà jointe à une demande.")
    if session.brief:
        # Une fiche par échange (un seul appel à l'IA) ; un nouvel essai renvoie la même fiche.
        return session
    ids = {q["id"] for q in session.questions}
    answers = {k: _line(v, 200) for k, v in (answers or {}).items() if k in ids and _line(v, 200)}
    trade = session.trade
    trade_slug, trade_name = (trade.slug, trade.name) if trade else ("", "")
    answered = [(q["question"], answers[q["id"]]) for q in session.questions if q["id"] in answers]
    brief = None
    if session.mode == M.AI and available():
        with suppress(ai.JefUnavailable):
            brief = _clean_brief(ai.brief(session.text, trade_name, answered))
    if not brief or not brief["title"] or not brief["description"]:
        session.mode = M.GUIDE  # la fiche vient du mode guidé : on le note
        brief = _clean_brief(
            guide.brief(session.text, trade_slug, trade_name, session.questions, answers)
        )
    if guide.danger(session.text):
        brief["urgent"] = True
    session.answers = answers
    session.brief = brief
    session.save(update_fields=["answers", "brief", "mode", "updated_at"])
    return session


def attach(client, req, session_id) -> None:
    """Joint la fiche Jef à la demande que le client vient de publier (si elle est à lui)."""
    session = JefSession.objects.filter(
        pk=session_id, client=client, request__isnull=True, brief__isnull=False
    ).first()
    if session:
        session.request = req
        session.save(update_fields=["request", "updated_at"])
